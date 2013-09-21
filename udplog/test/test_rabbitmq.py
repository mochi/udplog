# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Tests for L{udplog.rabbitmq}.
"""

from __future__ import division, absolute_import

import simplejson

from twisted.internet import defer
from twisted.internet import error
from twisted.internet import task
from twisted.trial import unittest

from txamqp.protocol import AMQClient

from udplog import rabbitmq
from udplog import twisted


class FakeAMQChannel(object):
    """
    Fake AMQ channel that logs all calls to C{basic_publish}.
    """
    def __init__(self):
        self.published = []


    def basic_publish(self, **kwargs):
        self.published.append(kwargs)
        return defer.Deferred()



class RabbitMQPublisherTest(unittest.TestCase):
    """
    Tests for L{udplog.rabbitmq.RabbitMQPublisherTest}.
    """

    def setUp(self):
        self.publisher = rabbitmq.RabbitMQPublisher(None)


    def test_sendEvent(self):
        """
        An event is encoded to JSON and then sent to the channel.
        """
        self.publisher.chan = FakeAMQChannel()
        event = {'message': 'test',
                 'timestamp': 1340634165}
        self.publisher.sendEvent(event)

        output = self.publisher.chan.published[-1]
        body = output['content'].body
        eventDict = simplejson.loads(body)

        self.assertEqual("test", eventDict['message'])


    def test_sendEventTimestampString(self):
        """
        The event timestamp is converted to a string before sending it.
        """
        self.publisher.chan = FakeAMQChannel()
        event = {'message': 'test',
                 'timestamp': 1340634165}
        self.publisher.sendEvent(event)

        output = self.publisher.chan.published[-1]
        body = output['content'].body
        eventDict = simplejson.loads(body)

        self.assertEqual("1340634165", eventDict['timestamp'])
        self.assertEqual(1340634165, event['timestamp'])


    def test_sendEventIsErrorBoolean(self):
        """
        If 'isError' is present, it is converted to a boolean.
        """
        self.publisher.chan = FakeAMQChannel()
        event = {'message': 'test',
                 'timestamp': 1340634165,
                 'isError': 1}
        self.publisher.sendEvent(event)

        output = self.publisher.chan.published[-1]
        body = output['content'].body
        eventDict = simplejson.loads(body)

        self.assertIsInstance(eventDict['isError'], bool)
        self.assertTrue(eventDict['isError'])


    def test_connectionLost(self):
        """
        The producer is unregistered at the dispatcher on lost connection.
        """
        connectionLostCalls = []
        callbackCalls = []

        def connectionLost(self, reason):
            connectionLostCalls.append(reason)

        def cb(event):
            raise Exception("Unexpected callback")

        # Set up publisher as if connected
        clock = task.Clock()
        self.publisher.producer = twisted.QueueProducer(callback=cb,
                                                       clock=clock)
        self.publisher.producer.resumeProducing()
        self.publisher.dispatcher = twisted.DispatcherFromUDPLogProtocol()
        self.publisher.dispatcher.register(self.publisher.producer.put)

        # Patch parent class to test up-call
        self.patch(AMQClient, 'connectionLost', connectionLost)

        # Drop connection
        self.publisher.connectionLost(error.ConnectionDone())
        self.assertEqual(1, len(connectionLostCalls))
        self.assertEqual(1, len(self.flushLoggedErrors(error.ConnectionDone)))

        # Test that the producer was unregistered with the dispatcher
        event = {'message': 'test'}
        self.publisher.dispatcher.eventReceived(event)
        clock.advance(0)
        self.assertEqual(0, len(callbackCalls))



