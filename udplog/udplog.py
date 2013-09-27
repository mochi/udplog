# -*- test-case-name: udplog.test.test_udplog -*-
#
# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Send and receive structured log events over UDP.

This module provides L{UDPLogger} for sending out structured log events. When
used as a script it listens for log events and prints them to standard out.

While this module uses a few helper functions from Twisted, it does not depend
on the Twisted reactor and can be used in any Python project.
"""

from __future__ import division, absolute_import

import logging
import socket
import time

import simplejson

from twisted.python import reflect
from twisted.python.failure import Failure

MAX_TRIMMED_MESSAGE_SIZE = 200

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 55647

# As LogRecord instances will get elements of the 'extra' keyword argument
# to the logging methods bolted on it as attributes, we need to know which
# fields are the non-extra ones. The following creates an empty LogRecord
# to list the fields it sets by default.
__emptyLogRecord = logging.LogRecord(None, None, None, None, None, None, None)
_DEFAULT_LOGGING_ATTRIBUTES = ['message', 'asctime']
_DEFAULT_LOGGING_ATTRIBUTES.extend(vars(__emptyLogRecord).keys())
del __emptyLogRecord

def unserialize(msg):
    """
    Unserialize a log event.

    A log event is defined as a category, followed by a colon, optional
    whitespace and a event dictionary serialized as JSON.

    @return: The category and event dictionary.
    @rtype: C{tuple} of (C{unicode} and C{dict}.
    """

    category, data = msg.split(':', 1)
    return category, simplejson.loads(data)



def augmentWithFailure(eventDict, failure, why=None):
    """
    Augment a log event with exception information.
    """
    eventDict['excText'] = failure.getTraceback()
    eventDict['excType'] = reflect.qual(failure.type)
    eventDict['excValue'] = reflect.safe_str(failure.value)
    eventDict.setdefault('logLevel', 'ERROR')

    eventDict['message'] = (why or
                            eventDict['excValue'] or
                            eventDict['excType'])



class MemoryLogger(object):
    """
    Keeper of all logs in memory.
    """

    def __init__(self):
        self.logged = []


    def log(self, category, eventDict):
        self.logged.append((category, eventDict))



class UDPLogger(object):
    """
    Dispatcher of structured log events over UDP.
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                       defaultFields=None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.connect((host, port))

        self.defaultFields = defaultFields or {}


    def augment(self, eventDict):
        newEventDict = {}
        newEventDict.setdefault('timestamp', time.time())
        newEventDict.update(self.defaultFields)
        newEventDict.update(eventDict)
        return newEventDict


    def serialize(self, category, eventDict):
        """
        Serialize a log event.

        The dictionary is serialized to JSON. To minimize serialization
        failures, for unserializable objects it falls back to the L{repr} of
        such objects.

        @type category: C{str}.
        @type eventDict: L{dict}.
        """
        msg = simplejson.dumps(eventDict,
                               default=lambda x: str(repr(x)),
                               skipkeys=True)
        return "%s:\t%s" % (category, msg)


    def serializeFailure(self, category, eventDict, size, failure, why):
        """
        Serialize a log event for a failed attempt to send a udplog event.

        If present, this truncates the C{'message'} field to
        C{MAX_TRIMMED_MESSAGE_SIZE}, and preserves exception-related fields
        from the original C{eventDict} as C{'original'}.
        """
        newEventDict = {
            'logLevel': 'WARNING',
            'original': {
                'category': category,
                'timestamp': eventDict['timestamp'],
                },
            }

        augmentWithFailure(newEventDict, failure, why)

        # include (trimmed) original message text
        if 'message' in eventDict:
            text = eventDict['message']
            if len(text) > MAX_TRIMMED_MESSAGE_SIZE:
                newEventDict['original_message_size'] = len(text)
                text = text[:MAX_TRIMMED_MESSAGE_SIZE-4] + '[..]'
            newEventDict['original']['message'] = text

        for key in ('logLevel', 'logName', 'excText', 'excType', 'excValue',
                    'lineno', 'filename', 'funcName'):
            if key in eventDict:
                newEventDict['original'][key] = eventDict[key]

        newEventDict['original_size'] = size

        return self.serialize('udplog', newEventDict)


    def log(self, category, eventDict):
        """
        Log an event.

        @param category: A short string identifying the type of log event.
            The receiving log server may use this to collect all messages of the
            same category in their own log files.
        @type category: C{bytes}

        @param eventDict: The event dictionary. As this is serialized to JSON
            (see L{serialize}), for complex values, you may want to render them
            to a string before adding them to the event dictionary.
        @type eventDict: C{dict}
        """
        eventDict = self.augment(eventDict)
        data = self.serialize(category, eventDict)

        try:
            self.socket.send(data)
        except:
            failure = Failure()
            why = "Failed to send udplog message"
            data = self.serializeFailure(category, eventDict, len(data),
                                         failure, why)
            try:
                self.socket.send(data)
            except Exception:
                import sys
                text = why + '\n' + failure.getBriefTraceback()
                print >> sys.stderr, text



class UDPLogHandler(logging.Handler):
    """
    Python Logging handler that emits to UDP.
    """

    def __init__(self, logger, category='python_logging'):
        """
        @type logger: L{UDPLogger}.
        """
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter())

        self.logger = logger
        self.category = category


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
                    'timestamp': record.created,
                    }

            if isinstance(record.args, dict):
                eventDict.update(record.args)

            extra = {name: value for name, value in vars(record).iteritems()
                     if name not in _DEFAULT_LOGGING_ATTRIBUTES}

            eventDict.update(extra)

            # Format the message for its side effects and extract the message
            # and exception information
            self.format(record)
            eventDict['message'] = record.message
            if record.exc_info:
                eventDict['excText'] = record.exc_text
                eventDict['excType'] = reflect.qual(record.exc_info[0])
                eventDict['excValue'] = reflect.safe_str(record.exc_info[1])

            # Extract the category, possibly overridden from record.args.
            category =  eventDict['category']
            del eventDict['category']


            self.logger.log(category, eventDict)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)



class ConfigurableUDPLogHandler(UDPLogHandler):
    """
    Configurable UDPLog logging handler.

    This is a convenience subclass of UDPLogHandler for use in logging
    configuration files (see L{logging.config.fileConfig})::

        [loggers]
        keys = root

        [handlers]
        keys = udplog

        [formatters]
        keys =

        [logger_root]
        level = INFO
        handlers = udplog

        [handler_udplog]
        class = udplog.udplog.ConfigurableUDPLogHandler
        level = INFO
        args = ({'appname': 'example'},)

    @note: This is a subclass instead of a factory function because
        L{logging.config} requires this.
    """


    def __init__(self, defaultFields=None, category='python_logging',
                       host=DEFAULT_HOST, port=DEFAULT_PORT,
                       includeHostname=True):
        """
        Set up a UDPLogHandler with a UDPLogger.

        @param defaultFields: Mapping of default fields to include in all
            events.
        @type defaultFields: L{dict}.

        @param category: The UDPLog category.
        @type category: L{bytes}.

        @param host: The UDP host to send to.
        @type host: L{bytes}.

        @param port: The UDP port to send to.
        @type host: L{int}.

        @param includeHostname: If set, the default fields include a
            C{'hostname'} field set to the current hostname.
        @type includeHostname: L{bool}.
        """
        defaultFields = defaultFields or {}

        if includeHostname:
            defaultFields.setdefault('hostname', socket.gethostname())

        logger = UDPLogger(host=host, port=port, defaultFields=defaultFields)
        UDPLogHandler.__init__(self, logger, category)



def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((DEFAULT_HOST, DEFAULT_PORT))
    while True:
        data, addr = sock.recvfrom(65535)
        print data.rstrip()



if __name__ == '__main__':
    main()
