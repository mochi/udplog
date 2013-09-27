# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Tests for L{udplog.udplog}.
"""

from __future__ import division, absolute_import

import errno
import logging
import socket
import sys
import time

import StringIO

from twisted.trial import unittest

from udplog import udplog

class UDPLoggerTest(unittest.TestCase):
    """
    Tests for {udplog.udplog.UDPLogger}.
    """

    MAX_DATAGRAM_SIZE = 8192

    def setUp(self):
        self.output = []


    def send(self, data):
        """
        Fake socket.send that records all log events.
        """
        if len(data) > self.MAX_DATAGRAM_SIZE:
            raise socket.error(errno.EMSGSIZE, "Message too long")
        else:
            self.output.append(data)


    def _catchOutput(self, logger):
        self.patch(logger.socket, "send", self.send)
        return logger


    def test_log(self):
        """
        A log event is serialized and sent out over UDP.
        """
        logger = udplog.UDPLogger()
        self._catchOutput(logger)

        logger.log('test', {u'message': u'test'})

        self.assertEqual(1, len(self.output))

        msg = self.output[0]
        self.assertRegexpMatches(msg, r'^test:\t{.*}$')

        category, eventDict = udplog.unserialize(msg)

        self.assertEqual(b'test', category)
        self.assertIn(u'message', eventDict)
        self.assertEqual(u'test', eventDict[u'message'])


    def test_logNotDict(self):
        """
        If eventDict is not a dict, TypeError is raised.
        """
        logger = udplog.UDPLogger()
        self.assertRaises(TypeError, logger.log, 'acategory', 1)


    def test_logObjects(self):
        """
        Arbitrary objects do not choke the JSON encoding.
        """
        class Something(object):
            pass

        something = Something()

        logger = udplog.UDPLogger()
        self._catchOutput(logger)
        logger.log('atest', {u'something': something})

        category, eventDict = udplog.unserialize(self.output[0])
        self.assertEqual(repr(something), eventDict[u'something'])


    def test_logNonUnicode(self):
        """
        Non-utf8-encodable dicts raise a UnicodeDecodeError.

        Ensure passing an *utf8 encodable* dict to udplog, otherwise you will
        make simplejson cry.
        """
        logger = udplog.UDPLogger()
        self.assertRaises(UnicodeDecodeError, logger.log,
                          'atest', {u'good': u'abc', u'bad': b'\x80abc' })


    def test_logTooLong(self):
        """
        If the log event is too long to fit in a UDP datagram, send regrets.
        """
        logger = udplog.UDPLogger()
        self._catchOutput(logger)

        logger.log('atest', {u'message': u'a' * self.MAX_DATAGRAM_SIZE,
                             u'timestamp': 1357328823.75116})

        self.assertEqual(1, len(self.output))
        category, eventDict = udplog.unserialize(self.output[0])

        self.assertEqual('udplog', category)
        self.assertEqual(u'Failed to send udplog message',
                         eventDict[u'message'])
        self.assertEqual(u'socket.error', eventDict['excType'])
        self.assertEqual(u'[Errno %d] Message too long' % errno.EMSGSIZE,
                         eventDict[u'excValue'])
        self.assertIn(u'excText', eventDict)
        self.assertEqual(u'WARNING', eventDict[u'logLevel'])

        # Check trimmed original
        original = eventDict[u'original']
        self.assertEqual(u'atest', original[u'category'])
        self.assertEqual(1357328823.75116, original[u'timestamp'])
        self.assertEqual(u'a' * (udplog.MAX_TRIMMED_MESSAGE_SIZE - 4) + '[..]',
                         original[u'message'])

        self.assertEqual(self.MAX_DATAGRAM_SIZE,
                         eventDict[u'original_message_size'])
        self.assertLess(self.MAX_DATAGRAM_SIZE,
                        eventDict[u'original_size'])


    def test_logTooLongAdditionalFields(self):
        """
        If the log event is too long, keep several fields.
        """
        logger = udplog.UDPLogger()
        self._catchOutput(logger)

        eventDict = {
            u'message': u'a' * self.MAX_DATAGRAM_SIZE,
            u'timestamp': 1357328823.75116,
            u'logLevel': u'ERROR',
            u'logName': __name__,
            u'excType': u'exceptions.ValueError',
            u'excValue': 'Oops',
            u'excText': u'exceptions.ValueError: Oops',
            u'filename': __file__,
            u'lineno': 4,
            u'funcName': u'test_log_too_long_additional_fields',
            u'foo': u'bar',
            }

        logger.log('atest', eventDict)
        self.assertEqual(1, len(self.output))

        category, failEventDict = udplog.unserialize(self.output[0])
        original = failEventDict[u'original']

        self.assertEqual(eventDict[u'logLevel'], original[u'logLevel'])
        self.assertEqual(eventDict[u'logName'], original[u'logName'])
        self.assertEqual(eventDict[u'excType'], original[u'excType'])
        self.assertEqual(eventDict[u'excValue'], original[u'excValue'])
        self.assertEqual(eventDict[u'excText'], original[u'excText'])
        self.assertEqual(eventDict[u'filename'], original[u'filename'])
        self.assertEqual(eventDict[u'lineno'], original[u'lineno'])
        self.assertEqual(eventDict[u'funcName'], original[u'funcName'])
        self.assertNotIn(u'foo', original)


    def test_logTooLongCategory(self):
        """
        If the log category is way too long, an exception is printed to stderr.
        """
        logger = udplog.UDPLogger()
        self._catchOutput(logger)

        eventDict = {
            u'message': u'a' * self.MAX_DATAGRAM_SIZE,
            u'timestamp': 1357328823.75116,
            }

        self.addCleanup(setattr, sys, 'stderr', sys.stderr)
        sys.stderr = StringIO.StringIO()

        logger.log(u'a' * self.MAX_DATAGRAM_SIZE, eventDict)
        self.assertEqual(0, len(self.output))
        self.assertRegexpMatches(
            sys.stderr.getvalue(),
            r'^Failed to send udplog message\n.*Message too long')


    def test_augmentTimestamp(self):
        """
        Every log event gets a timestamp if not already set.
        """
        logger = udplog.UDPLogger()
        self._catchOutput(logger)

        before = time.time()
        logger.log('test', {u'message': u'test'})
        after = time.time()

        category, eventDict = udplog.unserialize(self.output[0])

        self.assertIn(u'timestamp', eventDict)

        timestamp = eventDict[u'timestamp']
        self.assertGreaterEqual(timestamp, before)
        self.assertLessEqual(timestamp, after)


    def test_augmentDefaultFields(self):
        """
        Every log event gets default fields.
        """
        defaultFields = {u'hostname': u'foo.example.org'}

        logger = udplog.UDPLogger(defaultFields=defaultFields)
        self._catchOutput(logger)

        logger.log('test', {u'message': u'test'})

        category, eventDict = udplog.unserialize(self.output[0])

        self.assertIn(u'hostname', eventDict)
        self.assertEqual(u'foo.example.org', eventDict[u'hostname'])


    def test_augmentDefaultFieldsOverride(self):
        """
        Default fields can be overridden in individual events.
        """
        defaultFields = {u'hostname': u'foo.example.org'}

        logger = udplog.UDPLogger(defaultFields=defaultFields)
        self._catchOutput(logger)

        logger.log('test', {u'message': u'test',
                            u'hostname': u'bar.example.org'})

        category, eventDict = udplog.unserialize(self.output[0])

        self.assertIn(u'hostname', eventDict)
        self.assertEqual(u'bar.example.org', eventDict[u'hostname'])



class UDPLogHandlerTest(unittest.TestCase):
    """
    Tests for L{udplog.logging.UDPLogHandler}.
    """

    def setUp(self):
        self.udplogger = udplog.MemoryLogger()
        self.handler = udplog.UDPLogHandler(self.udplogger, category='test')
        self.logger = logging.Logger('test_logger')
        self.logger.addHandler(self.handler)


    def test_emit(self):
        """
        A message logged through python logging is sent out over udp.
        """
        self.logger.debug("Hello")

        self.assertEqual(1, len(self.udplogger.logged))
        category, eventDict = self.udplogger.logged[-1]

        self.assertEqual('Hello', eventDict.get('message'))
        self.assertEqual('DEBUG', eventDict.get('logLevel'))
        self.assertEqual('test_logger', eventDict.get('logName'))
        self.assertIn('timestamp', eventDict)


    def test_emitFormatted(self):
        """
        Messages are formatted and arguments are included in the event.
        """
        self.logger.debug("Hello, %(object)s!", {'object': "world"})

        self.assertEqual(1, len(self.udplogger.logged))
        category, eventDict = self.udplogger.logged[-1]

        self.assertEqual('Hello, world!', eventDict.get('message'))
        self.assertEqual('world', eventDict.get('object'))


    def test_emitException(self):
        """
        Logging an exception renders the traceback.
        """
        try:
            {}['something']
        except Exception:
            self.logger.exception('Oops')

        self.assertEqual(1, len(self.udplogger.logged))
        _, eventDict = self.udplogger.logged[-1]

        self.assertEqual('Oops', eventDict.get('message'))
        self.assertEqual('ERROR', eventDict.get('logLevel'))
        self.assertEqual('exceptions.KeyError', eventDict.get('excType'))
        self.assertEqual("'something'", eventDict.get('excValue'))
        self.assertTrue(eventDict.get('excText').startswith('Traceback'))


    def test_emit_extra(self):
        """
        Values passed in the extra keyword argument are added to the eventDict.
        """
        self.logger.debug("Hello", extra={'foo': 'bar'})

        category, eventDict = self.udplogger.logged[-1]
        self.assertIn('foo', eventDict)
        self.assertEqual('bar', eventDict['foo'])



class UDPLogHandlerFactoryTest(unittest.TestCase):
    """
    Tests for L{udplog.ConfigurableUDPLogHandler}.
    """

    def test_argsDefaults(self):
        """
        Without arguments, the logger and handler have their defaults.
        """
        handler = udplog.ConfigurableUDPLogHandler()
        logger = handler.logger

        self.assertEquals('python_logging', handler.category)
        self.assertEquals(('127.0.0.1', 55647), logger.socket.getpeername())
        self.assertEquals({'hostname': socket.gethostname()},
                          logger.defaultFields)


    def test_args(self):
        """
        All arguments are passed on.
        """
        handler = udplog.ConfigurableUDPLogHandler({'foo': 'bar'}, 'test',
                                                   '10.0.0.1', 55648, False)
        logger = handler.logger

        self.assertEquals('test', handler.category)
        self.assertEquals(('10.0.0.1', 55648), logger.socket.getpeername())
        self.assertNotIn('hostname', logger.defaultFields)
        self.assertEquals('bar', logger.defaultFields['foo'])
