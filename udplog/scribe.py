# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Asynchronous Scribe client support.

This provides a Twisted based Scribe client with an asynchronous interface for
sending logs and a consumer for L{udplog.twisted.DispatcherFromUDPLogProtocol}.
"""

from __future__ import division, absolute_import

import copy
import logging

import simplejson

from twisted.internet import defer
from twisted.internet import protocol
from twisted.python import log

from scribe import scribe
from thrift.Thrift import TApplicationException, TMessageType
from thrift.protocol import TBinaryProtocol
from thrift.transport import TTwisted

class AsyncScribeClient(scribe.Client):
    """
    Asynchronous Scribe client.

    This derives from L{scribe.Client} to work with the Twisted Thrift
    transport and provide an asynchronous interface for L{Log}.

    @ivar _reqs: List of pending requests. When a result comes in, the
    associated deferred will be fired. If the connection is closed,
    the deferreds of the pending requests will be fired with an exception.
    """


    def __init__(self, transport, factory):
        """
        Set up a scribe client.

        @param transport: The transport of the connection to the Scribe
            server.

        @param factory: The protocol factory of the Thrift transport
            protocol.
        """
        scribe.Client.__init__(self, factory.getProtocol(transport))
        self._reqs = {}


    def Log(self, messages):
        """
        Log messages.

        @param messages: The messages to be sent.
        @type messages: C{list} of L{scribe.LogEntry}.

        @return: L{Deferred<twisted.internet.defer.Deferred>}.
        """
        d = defer.Deferred()
        self._reqs[self._seqid] = d
        self.send_Log(messages)
        return d


    def send_Log(self, messages):
        """
        Called to send log messages.
        """
        scribe.Client.send_Log(self, messages)
        self._seqid += 1


    def recv_Log(self, iprot, mtype, rseqid):
        """
        Called when the result of the log request was received.
        """
        if mtype == TMessageType.EXCEPTION:
            result = TApplicationException()
        else:
            result = scribe.Log_result()

        result.read(iprot)
        iprot.readMessageEnd()

        try:
            d = self._reqs.pop(rseqid)
        except KeyError:
            log.err(result, "Unexpected log result")

        if isinstance(result, Exception):
            d.errback(result)
        elif result.success is not None:
            d.callback(result.success)
        else:
            d.errback(TApplicationException(
                TApplicationException.MISSING_RESULT,
                'Log failed: unknown result'))



class ScribeProtocol(TTwisted.ThriftClientProtocol):
    """
    Scribe protocol.

    This connects an asynchronous Scribe client to a server and sends
    out log events from C{dispatcher}.
    """

    def __init__(self, dispatcher, minLogLevel=logging.INFO):
        self.dispatcher = dispatcher
        self.minLogLevel = minLogLevel

        factory = TBinaryProtocol.TBinaryProtocolFactory(strictRead=False,
                                                         strictWrite=False)
        TTwisted.ThriftClientProtocol.__init__(self, AsyncScribeClient,
                                                     factory)


    def connectionMade(self):
        """
        Add this protocol as a consumer of log events.
        """
        TTwisted.ThriftClientProtocol.connectionMade(self)
        self.dispatcher.register(self.sendEvent)


    def connectionLost(self, reason=protocol.connectionDone):
        """
        Remove this protocol as a consumer of log events.
        """
        self.dispatcher.unregister(self.sendEvent)
        TTwisted.ThriftClientProtocol.connectionLost(self, reason)


    def sendEvent(self, event):
        """
        Write an event to Scribe.
        """
        event = copy.copy(event)

        # Drop events with a log level lower than the configured minimum.
        logLevel = logging.getLevelName(event.get('logLevel', 'INFO'))
        if logLevel < self.minLogLevel:
            return

        category = event['category']
        del event['category']

        try:
            message = simplejson.dumps(event)
        except ValueError, e:
            log.err(e, "Could not encode event to JSON")
            return

        entry = scribe.LogEntry(category=category, message=message)
        d = self.client.Log(messages=[entry])
        d.addErrback(log.err)
