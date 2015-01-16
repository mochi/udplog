# -*- test-case-name: udplog.test.test_syslog -*-
#
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Syslog server support.

This provides support for receiving syslog messages and utilities for
further shipping similar to the native udplog protocol.
"""

from __future__ import division, absolute_import

import calendar
import re

from dateutil.parser import parse
from dateutil import tz

from twisted.internet.protocol import DatagramProtocol
from twisted.python import log

FACILITIES = [
    u'kern', u'user', u'mail', u'daemon', u'auth', u'syslog', u'lpr', u'news',
    u'uucp', u'cron', u'authpriv', u'ftp', u'ntp', u'audit', u'alert', u'at',
    u'local0', u'local1', u'local2', u'local3', u'local4', u'local5',
    u'local6', u'local7'
    ]

SEVERITIES = [
    u'emerg', u'alert', u'crit', u'err', u'warn', u'notice', u'info', u'debug'
    ]

LOG_LEVELS = {
    u'emerg': u'EMERGENCY',
    u'alert': u'ALERT',
    u'crit': u'CRITICAL',
    u'err': u'ERROR',
    u'warn': u'WARNING',
    u'notice': u'NOTICE',
    u'info': u'INFO',
    u'debug': u'DEBUG',
    }


RE_SYSLOG = re.compile(
    u"""
    ^
    <(?P<priority>\d+)>
    (?P<timestamp>\w\w\w[ ][ 123456789]\d[ ]\d\d:\d\d:\d\d)[ ]
    (?P<hostname>\w+)[ ]
    (?P<tag>\w+)(\[(?P<pid>\d+)\])?:[ ]?
    (?P<message>.*)
    $
    """,
    re.IGNORECASE | re.VERBOSE)



def parsePriority(priority):
    """
    Extract facility and severity from syslog priority.

    @param priority: Syslog priority. Between 0 and 191.
    @type priority: L{int}

    @return: Tuple of facility and severity names. See C{FACILITIES} and
        C{SEVERITIES}.
    @rtype: L{tuple} of L{unicode}

    @raise: L{IndexError} for invalid priority values.
    """
    facility, severity = divmod(priority, 8)
    return FACILITIES[facility], SEVERITIES[severity]



def parseSyslog(line, tzinfo):
    """
    Parse syslog log message.

    This parses a syslog message per RFC 3164 into a dictionary with keys
    C{'message'}, C{'timestamp'}, C{'facility'}, C{'severity'}, C{'hostname'},
    C{'tag'} and C{'pid'}. If the log line doesn't match the syntax defined in
    RFC 3164 it returns the entire line as the value of the C{'message'} key.

    The syslog timestamp format only specifies month, day and time, lacking
    year or timestamp information. L{dateutil} is used to fill in the blanks
    using the C{tzinfo} parameter. Most likely you want to pass
    L{dateutil.tz.gettz()} as the value, as this attempts to determine the
    system's time zone (e.g. from C{/etc/localtime}), which is most likely the
    same as the one used for logging the timezone-naive timestamps.

    If the timestamp cannot be parsed, the C{'timestamp'} key will be absent
    from the resulting dictionary. If there is no PID in square brackets
    directly following the tag, the C{'pid'} key will be absent. For invalid
    priority values, the C{'facility'} and C{'severity'} fields will be empty.

    @param line: Syslog log message.
    @type line: C{unicode}

    @param tzinfo: Timezone information to attach to syslog's timezone-naive
        timestamps.
    @type tzinfo: L{datetime.tzinfo}

    @return: Event dictionary. The C{'timestamp'} key will have a
        timezone-aware L{datetime.datetime} as value. All other values are
        L{unicode} strings.

    @rtype: L{dict}
    """
    eventDict = {}

    match = RE_SYSLOG.match(line)
    if match:
        try:
            facility, severity = parsePriority(int(match.group('priority')))
        except IndexError:
            pass
        else:
            eventDict['facility'] = facility
            eventDict['severity'] = severity

        try:
            dt = parse(match.group('timestamp'))
        except ValueError:
            log.err()
        else:
            dt = dt.replace(tzinfo=tzinfo)
            eventDict['timestamp'] = dt

        eventDict['hostname'] = match.group('hostname')
        eventDict['tag'] = match.group('tag')
        if match.group('pid'):
            eventDict['pid'] = match.group('pid')
        eventDict['message'] = match.group('message')
    else:
        eventDict['message'] = line

    return eventDict


def syslogToUDPLogEvent(eventDict):
    if 'timestamp' in eventDict:
        eventDict['timestamp'] = calendar.timegm(eventDict['timestamp'].utctimetuple())

    if 'tag' in eventDict:
        eventDict.setdefault('category', eventDict['tag'])
        eventDict.setdefault('appname', eventDict['tag'])
        del eventDict['tag']

    if 'severity' in eventDict:
        eventDict.setdefault('logLevel', LOG_LEVELS[eventDict['severity']])
        del eventDict['severity']

    return eventDict


class SyslogDatagramProtocol(DatagramProtocol):

    def __init__(self, callback):
        self.callback = callback


    def datagramReceived(self, datagram, addr):
        eventDict = parseSyslog(datagram.decode('utf-8'), tz.gettz())
        eventDict = syslogToUDPLogEvent(eventDict)
        self.callback(eventDict)
