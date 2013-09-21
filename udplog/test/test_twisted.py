# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Tests for L{udplog.twisted}.
"""

from __future__ import division, absolute_import

import logging

from zope.interface import verify

from twisted.internet import defer
from twisted.internet.interfaces import IPushProducer
from twisted.internet import task
from twisted.python import failure
from twisted.python import log
from twisted.trial import unittest

from udplog import twisted
from udplog import udplog

class UDPLogObserverTest(unittest.TestCase):
    """
    Tests for L{udplog.twisted.UDPLogObserver}.
    """

    def setUp(self):
        self.logger = udplog.MemoryLogger()
        self.observer = twisted.UDPLogObserver(self.logger,
                                               defaultCategory='test')
        self.publisher = log.LogPublisher()
        self.publisher.addObserver(self.observer.emit)


    def test_emit(self):
        """
        Minimal log event is passed to UDP log.
        """
        self.publisher.msg('Test')

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('test', category)
        self.assertEqual('Test', eventDict['message'])
        self.assertIn('timestamp', eventDict)
        self.assertNotIn('time', eventDict)
        self.assertEqual('INFO', eventDict['logLevel'])


    def test_emitCategory(self):
        """
        The value of key 'category' sets the UDP log category for the event.
        """
        self.publisher.msg('Test', category='other')

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('other', category)
        self.assertEqual('Test', eventDict['message'])


    def test_emitErr(self):
        """
        A typical error log event is passed to UDP log.

        This mimics how L{log.err} would call C{msg}.
        """
        self.publisher.msg(failure=failure.Failure(Exception("Test")),
                           why="Something went wrong",
                           isError=1)

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('Traceback (most recent call last):\n'
                         'Failure: exceptions.Exception: Test\n',
                         eventDict['excText'])
        self.assertEqual('exceptions.Exception', eventDict['excType'])
        self.assertEqual('Test', eventDict['excValue'])
        self.assertEqual('Something went wrong', eventDict['message'])
        self.assertNotIn('why', eventDict)
        self.assertNotIn('failure', eventDict)
        self.assertEqual('ERROR', eventDict['logLevel'])


    def test_emitErrNoWhy(self):
        """
        If there is no 'why' log the exception's message.
        """
        self.publisher.msg(failure=failure.Failure(Exception("Test")),
                           why=None,
                           isError=1)

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('Test', eventDict['message'])
        self.assertNotIn('why', eventDict)


    def test_emitErrNoWhyNoArgs(self):
        """
        If there is no 'why' and the exception has no message, log its class.
        """
        self.publisher.msg(failure=failure.Failure(Exception()),
                           why=None,
                           isError=1)

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('exceptions.Exception', eventDict['message'])


    def test_emitWarning(self):
        """
        A typical warning event is passed to UDP log.

        This mimics how warnings are picked up and logged.
        """
        self.publisher.msg(warning=UserWarning("Oops!"),
                           category='exceptions.UserWarning',
                           filename='test.py', lineno=342,
                           format='%(filename)s:%(lineno)s: '
                                  '%(category)s: %(warning)s')

        self.assertEqual(1, len(self.logger.logged))
        category, eventDict = self.logger.logged[-1]

        self.assertEqual('Oops!', eventDict['message'])
        self.assertNotIn('warning', eventDict)
        self.assertEqual('exceptions.UserWarning',
                         eventDict['warningCategory'])
        self.assertEqual('test.py', eventDict['filename'])
        self.assertEqual(342, eventDict['lineno'])
        self.assertEqual('test', category)
        self.assertEqual('WARNING', eventDict['logLevel'])


    def test_start(self):
        """
        Starting the observer adds it to the default log publisher.
        """
        self.observer.start()
        self.assertIn(self.observer.emit, log.theLogPublisher.observers)
        self.observer.stop()


    def test_stop(self):
        """
        Stopping the observer removes it from the default log publisher.
        """
        self.observer = twisted.UDPLogObserver(self.logger)
        self.observer.start()
        self.observer.stop()

        self.assertNotIn(self.observer.emit, log.theLogPublisher.observers)



class TwistedLogHandlerTest(unittest.TestCase):
    """
    Tests for L{udplog.twisted.TwistedLogHandler}.
    """

    def log(self, eventDict):
        self.logged.append(eventDict)


    def setUp(self):
        self.publisher = log.LogPublisher()
        self.publisher.addObserver(self.log)

        self.handler = twisted.TwistedLogHandler(publisher=self.publisher)
        self.logger = logging.Logger('test_logger')
        self.logger.addHandler(self.handler)

        self.logged = []


    def test_emit(self):
        """
        A message logged through python logging ends up in the observer.
        """
        self.logger.debug("Hallo")

        self.assertEqual(1, len(self.logged))
        eventDict = self.logged[-1]

        self.assertEqual('python_logging', eventDict.get('category'))
        self.assertEqual(('Hallo',), eventDict.get('message'))
        self.assertEqual('DEBUG', eventDict.get('logLevel'))
        self.assertEqual('test_logger', eventDict.get('logName'))
        self.assertFalse(eventDict.get('isError'))


    def test_emitException(self):
        """
        Logging an exception captures it in a Failure added to the event.
        """
        try:
            {}['something']
        except Exception:
            self.logger.exception('Oops')

        self.assertEqual(1, len(self.logged))
        eventDict = self.logged[-1]

        self.assertFalse(eventDict.get('message'))
        self.assertEqual('ERROR', eventDict.get('logLevel'))
        self.assertTrue(eventDict.get('isError'))
        self.assertEqual(KeyError, eventDict['failure'].type)
        self.assertEqual('Oops', eventDict['why'])


    def test_emitIsError(self):
        """
        Only messages with log level >= ERROR have isError True.
        """
        def checkIsError(logLevel):
            self.logger.log(logLevel, "Hallo")
            eventDict = self.logged[-1]
            return eventDict['isError']

        self.assertFalse(checkIsError(logging.DEBUG))
        self.assertFalse(checkIsError(logging.INFO))
        self.assertFalse(checkIsError(logging.WARNING))
        self.assertTrue(checkIsError(logging.ERROR))
        self.assertTrue(checkIsError(logging.CRITICAL))



class UDPLogProtocol(unittest.TestCase):
    """
    Tests for L{udplog.twisted.UDPLogProtocol}.
    """

    def setUp(self):
        self.events = []
        self.protocol = twisted.UDPLogProtocol()
        self.protocol.eventReceived = self.events.append


    def test_datagramReceived(self):
        """
        A datagram is a category, a colon and a JSON dict.
        """
        datagram = """test_category:\t{"key": "value"}"""
        self.protocol.datagramReceived(datagram, None)

        self.assertEqual(1, len(self.events))
        event = self.events[-1]

        self.assertEqual('test_category', event.get('category'))
        self.assertEqual('value', event.get('key'))


    def test_datagramReceivedNoMsg(self):
        """
        If there is no colon, a ValueError is logged.
        """
        datagram = """test_category"""
        self.protocol.datagramReceived(datagram, None)
        self.assertEqual(1, len(self.flushLoggedErrors(ValueError)))


    def test_datagramReceivedInvalidJSON(self):
        """
        If the event dictionary is not valid JSON, a ValueError is logged.
        """
        datagram = """test_category:\t{"key":"value"""
        self.protocol.datagramReceived(datagram, None)
        self.assertEqual(1, len(self.flushLoggedErrors(ValueError)))


    def test_datagramReceivedNotDict(self):
        """
        If the encoded JSON is not a dict, a TypeError is logged.
        """
        datagram = """test_category:\t3"""
        self.protocol.datagramReceived(datagram, None)
        self.assertEqual(1, len(self.flushLoggedErrors(TypeError)))



class DispatcherFromUDPLogProtocolTest(unittest.TestCase):
    """
    Tests for L{udplog.twisted.DispatcherFromUDPLogProtocol}.
    """

    def setUp(self):
        self.dispatcher = twisted.DispatcherFromUDPLogProtocol()


    def test_register(self):
        """
        A registered consumer will receive events when dispatched.
        """
        events = []
        self.dispatcher.register(lambda event: events.append(event))
        self.dispatcher.eventReceived(None)
        self.assertEqual([None], events)


    def test_registerMultiple(self):
        """
        Multiple registered consumers will receive events when dispatched.
        """
        events1 = []
        events2 = []
        self.dispatcher.register(lambda event: events1.append(event))
        self.dispatcher.register(lambda event: events2.append(event))
        self.dispatcher.eventReceived(None)
        self.assertEqual([None], events1)
        self.assertEqual([None], events2)


    def test_eventReceivedMultipleException(self):
        """
        A failed consumer does not affect others.
        """
        events = []
        def err(event):
            raise ValueError("Oops")
        self.dispatcher.register(err)
        self.dispatcher.register(lambda event: events.append(event))
        self.dispatcher.eventReceived(None)
        self.assertEqual([None], events)
        self.assertEqual(1, len(self.flushLoggedErrors(ValueError)))


    def test_unregister(self):
        """
        A unregistered consumer will not received events when dispatched.
        """
        events = []
        def consumer(event):
            events.append(event)

        self.dispatcher.register(consumer)
        self.dispatcher.unregister(consumer)
        self.dispatcher.eventReceived(None)
        self.assertEqual([], events)


    def test_unregisterUnknown(self):
        """
        Unknown consumers are silently ignored when unregistered.
        """
        def consumer(event):
            pass

        self.dispatcher.unregister(consumer)



class UDPLogClientFactoryTest(unittest.TestCase):
    """
    Tests for L{UDPLogClientFactory}.
    """

    def setUp(self):
        class TestProtocol(object):
            factory = None

            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        self.factory = twisted.UDPLogClientFactory(TestProtocol, 1, bar=2)


    def test_buildProtocol(self):
        """
        A protocol is created with the args and kwargs passed to the factory.
        """
        protocol = self.factory.buildProtocol(None)
        self.assertEqual((1,), protocol.args)
        self.assertEqual({'bar': 2}, protocol.kwargs)
        self.assertIdentical(self.factory, protocol.factory)


    def test_buildProtocolReset(self):
        """
        When a protocol is built, the factory reconnect delay is reset.
        """
        def protocol():
            pass

        self.factory.delay = self.factory.initialDelay + 5
        self.factory.buildProtocol(None)
        self.assertEqual(self.factory.initialDelay, self.factory.delay)



class QueueProducerTest(unittest.TestCase):
    """
    Tests for L{udplog.twisted.QueueProducer}.
    """

    def setUp(self):
        self.clock = task.Clock()
        self.output = []
        self.producer = twisted.QueueProducer(self.callback, clock=self.clock)


    def callback(self, obj):
        """
        Gets called to deliver an item, saving the item.
        """
        self.output.append(obj)
        return defer.succeed(None)


    def test_interface(self):
        """
        QueueProducer instances provide IPushProducer.
        """
        verify.verifyObject(IPushProducer, self.producer)


    def test_putBeforeResume(self):
        """
        If resumeProducing has never been called, all items are just queued.
        """
        self.producer.put(None)
        self.assertEqual(0, len(self.output))


    def test_putNotPaused(self):
        """
        When not paused has been called, all items are just queued.
        """
        self.producer.resumeProducing()
        self.producer.put(None)
        self.assertEqual(1, len(self.output))


    def test_processQueueReschedule(self):
        """
        After an item has been delivered, subsequent items should, too.
        """
        self.producer.resumeProducing()
        self.producer.put(None)
        self.assertEqual(1, len(self.output))

        self.producer.put(None)
        self.clock.advance(0)
        self.assertEqual(2, len(self.output))

        self.producer.put(None)
        self.producer.put(None)
        self.clock.advance(0)
        self.assertEqual(4, len(self.output))


    def test_processQueueRescheduleError(self):
        """
        Rescheduling happens if the callback returns a failure.
        """
        def callback(obj):
            if obj == 1:
                return defer.fail(ValueError())
            if obj == 2:
                self.output.append(obj)
                return defer.succeed(None)

        self.producer = twisted.QueueProducer(callback, clock=self.clock)
        self.producer.resumeProducing()
        self.producer.put(1)
        self.producer.put(2)
        self.clock.advance(0)
        self.assertEqual([2], self.output)
        self.assertEqual(1, len(self.flushLoggedErrors(ValueError)))



    def test_processQueueRescheduleRealReactor(self):
        """
        Rescheduling happens with the real reactor.
        """
        d = defer.Deferred()
        def callback(obj):
            if obj == 1:
                self.output.append(obj)
            if obj == 2:
                d.callback(obj)
            return defer.succeed(None)

        self.producer = twisted.QueueProducer(callback)
        self.producer.resumeProducing()
        self.producer.put(1)
        self.assertEqual(1, len(self.output))

        self.producer.put(2)
        return d


    def test_pauseProducing(self):
        """
        Items put while paused, are not delivered.
        """
        self.producer.resumeProducing()
        self.producer.pauseProducing()
        self.producer.put(None)
        self.clock.advance(0)
        self.assertEqual(0, len(self.output))


    def test_resumeProducing(self):
        """
        Items put while paused, are delivered after resuming.
        """
        self.producer.resumeProducing()
        self.producer.pauseProducing()
        self.producer.put(None)
        self.clock.advance(0)
        self.producer.resumeProducing()
        self.assertEqual(1, len(self.output))


    def test_stopProducingCancelReschedule(self):
        """
        Stop producing cancels reschedules.
        """
        self.producer.resumeProducing()
        self.producer.put(None)
        self.producer.pauseProducing()
        self.producer.put(None)
        self.producer.stopProducing()
        self.clock.advance(0)
        self.assertEqual(1, len(self.output))


    def test_stopProducingCancelDeferred(self):
        """
        Stop producing cancels the deferred to process the next item.
        """
        self.producer.resumeProducing()
        self.producer.stopProducing()
        self.producer.put(None)
        self.clock.advance(0)
        self.assertEqual(0, len(self.output))


    def test_processQueueRescheduleDeferred(self):
        """
        If the callback deferred fires after pausing, don't deliver.
        """
        d = defer.Deferred()

        def callback(obj):
            if obj == 1:
                return defer.succeed(None)
            elif obj == 2:
                return d
            else:
                self.output.append(obj)
                return defer.succeed(None)

        self.producer = twisted.QueueProducer(callback, clock=self.clock)
        self.producer.resumeProducing()
        self.producer.put(1)
        self.clock.advance(0)
        self.producer.put(2)
        self.producer.put(3)
        self.clock.advance(0)
        self.producer.pauseProducing()
        d.callback(None)
        self.clock.advance(0)
        self.producer.put(3)
        self.clock.advance(0)
        self.assertEqual(0, len(self.output))


    def test_processQueueResumeDeferredReuse(self):
        """
        Resuming right after pausing reuses the existing waiting deferred.
        """
        self.producer.resumeProducing()
        self.producer.put(1)
        self.clock.advance(0)
        self.producer.pauseProducing()
        d = self.producer.waiting
        self.producer.resumeProducing()
        self.clock.advance(0)
        self.assertIdentical(d, self.producer.waiting)


    def test_putLimitedQueue(self):
        """
        Putting items over the limit while paused keeps last n items.
        """
        self.producer = twisted.QueueProducer(self.callback, size=3,
                                             clock=self.clock)
        self.producer.resumeProducing()
        self.producer.pauseProducing()
        self.producer.put(1)
        self.producer.put(2)
        self.producer.put(3)
        self.producer.put(4)
        self.producer.resumeProducing()
        self.clock.advance(0)
        self.assertEqual([2, 3, 4], self.output)



