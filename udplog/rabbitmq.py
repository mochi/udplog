# -*- test-case-name: udplog.test.test_rabbitmq -*-
#
# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
RabbitMQ support.

This provides a Twisted based RabbitMQ client for pushing logs to a RabbitMQ
exchange. A service like Logstash can subscribe to such an exchange to further
process logs.
"""

from __future__ import division, absolute_import

import copy

import simplejson

from twisted.internet import defer
from twisted.python import log
from twisted.python.filepath import FilePath

import txamqp.spec
from txamqp.client import TwistedDelegate
from txamqp.content import Content
from txamqp.protocol import AMQClient

from udplog.twisted import QueueProducer

class RabbitMQPublisher(AMQClient):
    """
    Protocol for passing UDP Log events to Logstash via RabbitMQ.

    To handle push-back from the RabbitMQ server, log events are sent
    from a local in-memory queue. If L{queueSize} is set and the queue is full,
    old items are dropped in favor of the new ones.

    @ivar queueSize: Optional maximum queue size.
    """

    def __init__(self, dispatcher, username='guest', password='guest',
                       vhost='/', exchange='logs', queueSize=None):
        self.dispatcher = dispatcher
        self.username = username
        self.password = password
        self.exchange = exchange
        self.queueSize = queueSize

        self.chan = None

        specDir = FilePath(__file__).parent()
        specFilePath = specDir.child('amqp0-9-1.extended.xml')
        spec = txamqp.spec.load(specFilePath.path)

        delegate = TwistedDelegate()
        AMQClient.__init__(self, delegate=delegate, vhost=vhost,
                                 spec=spec)


    def connectionMade(self):
        """
        Add this protocol as a consumer of log events.
        """
        AMQClient.connectionMade(self)

        def eb(failure):
            log.err(failure)
            self.transport.loseConnection()

        d = self.gotConnection()
        d.addErrback(eb)


    @defer.inlineCallbacks
    def gotConnection(self):
        yield self.authenticate(username=self.username,
                                password=self.password, mechanism='PLAIN')

        self.chan = yield self.channel(1)
        yield self.chan.channel_open()

        yield self.chan.exchange_declare(exchange="logs", type="topic",
                                         durable=True, auto_delete=False)

        self.producer = QueueProducer(callback=self.sendEvent,
                                      size=self.queueSize)
        self.transport.registerProducer(self.producer, streaming=True)
        self.producer.resumeProducing()

        self.dispatcher.register(self.producer.put)


    def connectionLost(self, reason):
        """
        Remove this protocol as a consumer of log events.
        """
        self.chan = None
        self.dispatcher.unregister(self.producer.put)
        log.err(reason, "Connection lost")
        AMQClient.connectionLost(self, reason)


    def sendEvent(self, event):
        """
        Write an event to Logstash.
        """
        if not self.chan:
            log.msg("No AMQP channel. Dropping event.")
            return

        event = copy.copy(event)

        # Pass timestamp on as a string, to work around Logstash bug 279.
        event['timestamp'] = repr(event['timestamp'])

        # Make sure isError is always a boolean
        if 'isError' in event:
            event['isError'] = bool(event['isError'])

        body = simplejson.dumps(event)
        content = Content(body)
        return self.chan.basic_publish(exchange=self.exchange,
                                       content=content)
