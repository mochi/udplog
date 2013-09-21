# -*- test-case-name: udplog.test.test_scribe -*-
#
# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Twisted utilities for UDP logging.

This provides a Twisted protocol implementation of the UDP Log protocol,
a handler for passing messages from the Python logging system to the Twisted
Logging system and various helpers for creating a UDP Log server.
"""

from __future__ import division, absolute_import

from collections import deque
import logging

import simplejson

from zope.interface import implements

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet.interfaces import IPushProducer
from twisted.python import log
from twisted.python import reflect
from twisted.python.failure import Failure

from udplog import udplog

class UDPLogObserver(object):
    """
    Twisted Log Observer that emits to UDP log.

    @ivar defaultCategory: Defailt log category. If there is no key C{category}
        in the C{eventDict}, use this category instead.
    """

    def __init__(self, logger, defaultCategory='udplog_unknown'):
        self.logger = logger
        self.defaultCategory = defaultCategory


    def emit(self, eventDict):
        """
        Log an event.

        This converts C{eventDict} so that it can be serialized to JSON and
        sent over UDP to the logging server.

        The key C{'time'} that is automatically provided by Twisted is renamed
        to C{'timestamp'} that is used in UDP log.

        When Twisted logs an error, the associated Failure is in the
        C{eventDict} with key C{'failure'}. For warnings, C{'warning'} holds
        the warning class and its arguments, and C{'filename'}, C{'lineno'} the
        location where the warning was reported from. See
        L{twisted.python.log.textFromEventDict} for how C{'format'} is used to
        render failures and warnings.

        See L{twisted.python.log.ILogObserver}.
        """
        eventDict = eventDict.copy()
        eventDict['message'] = log.textFromEventDict(eventDict)
        eventDict['timestamp'] = eventDict['time']

        if 'warning' in eventDict:
            # Twisted passes the warning category in 'category' and the
            # warning instance in 'warning'. Override message to only contain
            # actual warning message and put the category in 'warning'.
            eventDict['message'] = reflect.safe_str(eventDict['warning'])
            eventDict['warningCategory'] = eventDict['category']
            eventDict.setdefault('logLevel', 'WARNING')
            del eventDict['category']
            del eventDict['warning']

        if 'isError' in eventDict:
            eventDict['isError'] = bool(eventDict['isError'])

        if eventDict.get('isError', False) and 'failure' in eventDict:
            # Twisted passed the failure instance in 'failure'. Add a field
            # 'excType' containing the exception type and remove 'failure'.
            # We always want to render the traceback in a separate field, so we
            # override the actual message that textFromEventDict created for
            # us.

            udplog.augmentWithFailure(eventDict,
                                      eventDict['failure'],
                                      eventDict['why']
                                      )
            del eventDict['why']
            del eventDict['failure']

        eventDict.setdefault('logLevel', 'INFO')

        # Clean up unneeded Twisted specific keys.
        #   * time is replaced by timeformat
        #   * format, if present, is used by textFromEventDict.
        for key in ('time', 'format'):
            if key in eventDict:
                del eventDict[key]

        category = eventDict.get('category', self.defaultCategory)

        self.logger.log(category, eventDict)


    def start(self):
        """
        Start observing log events.
        """
        log.addObserver(self.emit)


    def stop(self):
        """
        Stop observing log events.
        """
        log.removeObserver(self.emit)



class TwistedLogHandler(logging.Handler):

    def __init__(self, category='python_logging', publisher=None):
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter())

        self.category = category

        if publisher:
            self.publisher = publisher
        else:
            from twisted.python.log import theLogPublisher
            self.publisher = theLogPublisher


    def emit(self, record):
        """
        Emit a record.
        """
        try:
            eventDict = {
                    'category': self.category,
                    'logLevel': record.levelname,
                    'logName': record.name,
                    'filename': record.pathname,
                    'lineno': record.lineno,
                    'funcName': record.funcName,
                    }

            eventDict['isError'] = record.levelno >= logging.ERROR

            if isinstance(record.args, dict):
                eventDict.update(record.args)

            message = record.getMessage()

            if record.exc_info:
                exc_type, exc_value, exc_traceback = record.exc_info
                eventDict['failure'] = Failure(exc_value,
                                               exc_type,
                                               exc_traceback)
                self.publisher.msg(why=message, **eventDict)
            else:
                self.publisher.msg(message, **eventDict)

        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)



class UDPLogProtocol(protocol.DatagramProtocol):
    """
    UDP Log protocol.

    Log events are received as combination of category and a message, separated
    by a colon. This message is a dictionary encoded in JSON. Upon receiving
    an event, it is decoded and passed to L{eventReceived}.
    """

    def datagramReceived(self, datagram, addr):
        data = datagram.rstrip()

        try:
            category, event = udplog.unserialize(data)
            event['category'] = category
        except (ValueError, TypeError):
            log.err()
            return

        self.eventReceived(event)


    def eventReceived(self, event):
        """
        A log event was received.

        Override this method to process events.
        """



class DispatcherFromUDPLogProtocol(UDPLogProtocol):
    """
    Adapter from UDPLogProtocol to a consumer of log events.
    """

    def __init__(self):
        self._consumers = set()


    def register(self, consumer):
        self._consumers.add(consumer)


    def unregister(self, consumer):
        try:
            self._consumers.remove(consumer)
        except KeyError:
            pass


    def eventReceived(self, event):
        for consumer in self._consumers:
            try:
                consumer(event)
            except:
                log.err()



class QueueProducer(object):
    """
    Push producer with a queue.

    This producer accepts items with L{put} that will be delivered to
    the passed callback if not paused. If the producer is paused, the
    items get put in a queue. The queue may be limited in size, which
    causes it to only queue the last n items. Upon resuming, items from
    the queue will be passed to the callback again.

    When the deferred returned by the callback fires, the delivery of the
    next item in the queue will be scheduled.
    """

    implements(IPushProducer)

    def __init__(self, callback, size=None, clock=None):
        """
        @param callback: Callback method that gets items passed to L{put}
            whenever the producer is not paused. The callback returns
            a deferred that is waited upon before processing the next
            item.

        @param size: Optional queue size. If the queue becomes full, old
            items are dropped.

        @param clock: An object which provides
            L{twisted.internet.interfaces.IReactorTime}.
        """
        self.callback = callback
        self.paused = True
        self.waiting = None
        self.pending = deque(maxlen=size)

        if clock is None:
            from twisted.internet import reactor
            clock = reactor
        self._clock = clock

        self._call = None


    def pauseProducing(self):
        """
        Called when the transport wants to pause receiving data.
        """
        log.msg(format="Pause producing for %(callback)s.",
                       callback=self.callback)
        self.paused = True


    def resumeProducing(self):
        """
        Called when the transport is ready to resume receiving data.
        """
        log.msg(format="Resume producing for %(callback)s.",
                       callback=self.callback)
        self.paused = False
        self._processQueue()


    def stopProducing(self):
        """
        Called when the transport can no longer deliver data.
        """
        if self.waiting:
            self.waiting.cancel()
        if self._call:
            self._call.cancel()


    def put(self, obj):
        """
        Put a new item for delivery to the protocol using the callback.
        """
        if self.waiting and not self.paused:
            d = self.waiting
            self.waiting = None
            d.callback(obj)
        else:
            self.pending.append(obj)


    def _processQueue(self):
        """
        Process the next item in queue.
        """
        self._call = None

        def reschedule(_):
            self._call = self._clock.callLater(0, self._processQueue)

        def processItem(obj):
            d = self.callback(obj)
            d.addErrback(log.err)
            d.addCallback(reschedule)
            return d

        if self.pending and not self.paused:
            obj = self.pending.popleft()
            processItem(obj)
        elif not self.waiting:
            def canceller(_):
                self.waiting = None
            def trapCancelledError(failure):
                failure.trap(defer.CancelledError)
            d = defer.Deferred(canceller=canceller)
            d.addCallback(processItem)
            d.addErrback(trapCancelledError)
            d.addErrback(log.err)
            self.waiting = d
        else:
            # Reuse existing waiting deferred
            pass



class UDPLogClientFactory(protocol.ReconnectingClientFactory):
    """
    Reconnecting client factory that resets retry delay upon connecting.
    """
    maxDelay = 30

    def __init__(self, protocolClass, *args, **kwargs):
        """
        Initialize the factory.

        @param protocolClass: The class to build a protocol with.
        @type protocolClass: L{twisted.internet.interfaces.IProtocol} provider.

        @param maxDelay: Maximum number of seconds between connection
            attempts.
        @type maxDelay: C{float}.
        """
        self.protocol = protocolClass
        self.args = args
        self.kwargs = kwargs


    def buildProtocol(self, addr):
        """
        Create a protocol and reset the retry delay.
        """
        self.resetDelay()
        p = self.protocol(*self.args, **self.kwargs)
        p.factory = self
        return p



class UDPLogToTwistedLog(object):
    """
    Consumer for L{DispatcherFromUDPLogProtocol} that logs to Twisted log.
    """

    def __init__(self, dispatcher):
        dispatcher.register(self.sendEvent)


    def sendEvent(self, eventDict):
        log.msg(simplejson.dumps(eventDict, indent=4, sort_keys=True))
