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
import json
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
    (?P<content>(?P<message>.*?)
    ([ ]?@cee:[ ](?P<cee>.*))?)
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

    If the message has the C{'@cee:'} marker, the rest of the message
    is interpreted as a JSON object and merged into the resulting event
    dictionary. See U{Mitre CEE<https://cee.mitre.org/>}. Note that no
    attempt is made to interpret the field names. It is advisable to explicitly
    set the C{category} field to provide a namespace for the other fields, as
    this helps type mapping to storage facilities like Elasticsearch.

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

        if match.group('cee'):
            try:
                cee = json.loads(match.group('cee'))
            except:
                log.err()
                eventDict['message'] = match.group('content')
            else:
                eventDict.update(cee)
    else:
        eventDict['message'] = line

    return eventDict



def syslogToUDPLogEvent(eventDict, hostnames=None):
    """
    Convert syslog event to a UDPLog event.

    This converts the timestamp to POSIX style and renames the C{tag}
    and C{severity} fields into respectively C{appname} and C{logLevel} for
    consistency in field naming.

    Additionally, this sets the C{category} field to C{'syslog'} if not set
    through the use of CEE.

    @param eventDict: The event dictionary.
    @type eventDict: C{dict}

    @param hostnames: Map to rewrite hostnames.
    @type hostnames: L{dict}
    """
    if 'timestamp' in eventDict:
        eventDict['timestamp'] = calendar.timegm(
            eventDict['timestamp'].utctimetuple())

    eventDict.setdefault('category', u'syslog')

    if 'tag' in eventDict:
        eventDict['appname'] = eventDict['tag']
        del eventDict['tag']

    if 'severity' in eventDict:
        eventDict['logLevel'] = LOG_LEVELS[eventDict['severity']]
        del eventDict['severity']

    if (hostnames and eventDict.get('hostname') in hostnames):
        eventDict['hostname'] = hostnames[eventDict['hostname']]

    return eventDict



class SyslogDatagramProtocol(DatagramProtocol):
    """
    Datagram protocol for syslog.

    This can be used with
    C{UNIXDatagramServer<twisted.application.internet.UNIXDatagramServer} or
    C{UDPServer<twisted.application.internet.UDPServer} to accept syslog events
    over UNIX sockets or UDP respectively. See L{udplog.tap} for examples.
    """

    def __init__(self, callback, hostnames=None):
        """
        @param callback: Callback function that is called with a parsed
            syslog event, with fields made consistent for UDPLog. See
            L{parseSyslog} and L{syslogToUDPLogEvent} for details.
        """
        self._callback = callback
        self._hostnames = hostnames


    def datagramReceived(self, datagram, addr):
        eventDict = parseSyslog(datagram.decode('utf-8'), tz.gettz())
        eventDict = syslogToUDPLogEvent(eventDict, self._hostnames)
        self._callback(eventDict)
