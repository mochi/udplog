from dateutil import tz
import datetime

from twisted.trial.unittest import TestCase

from udplog import syslog

class ParsePriorityTests(TestCase):

    def test_priority13(self):
        self.assertEquals(('user', 'notice'), syslog.parsePriority(13))


    def test_priority29(self):
        self.assertEquals(('daemon', 'notice'), syslog.parsePriority(29))



class ParseSyslogTests(TestCase):

    def setUp(self):
        self.tz = tz.gettz('Europe/Amsterdam')


    def test_priority(self):
        """
        The priority is extracted and decoded into facility and severity.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('user', result['facility'])
        self.assertEquals('notice', result['severity'])


    def test_message(self):
        """
        The message is extracted from the log line.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('hello', result['message'])


    def test_timestamp(self):
        """
        Timestamp is converted to a L{datetime} in the given timezone.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        timestamp = datetime.datetime(2015, 1, 15, 15, 59, 26, tzinfo=tz.tzutc())
        self.assertEquals(timestamp, result['timestamp'])


    def test_timestampOtherZone(self):
        """
        Timestamp is converted to a L{datetime} in the other timezone.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, tz.gettz('America/Los Angeles'))
        timestamp = datetime.datetime(2015, 1, 16, 00, 59, 26, tzinfo=tz.tzutc())
        self.assertEquals(timestamp, result['timestamp'])


    def test_timestampSingleDigitDay(self):
        """
        Single digit days are parsed correctly.
        """
        line = "<13>Jan  5 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        timestamp = datetime.datetime(2015, 1, 5, 15, 59, 26, tzinfo=tz.tzutc())
        self.assertEquals(timestamp, result['timestamp'])


    def test_timestampInvalid(self):
        """
        Invalid dates result in no timestamp, error logged.
        """
        line = "<13>Foo 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        self.assertNotIn('timestamp', result)
        self.assertEqual(1, len(self.flushLoggedErrors(ValueError)))


    def test_hostname(self):
        """
        The hostname is extracted.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('myhost', result['hostname'])


    def test_tag(self):
        """
        The tag is extracted.
        """
        line = "<13>Jan 15 16:59:26 myhost test: hello"
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('test', result['tag'])


    def test_tagFollowedByPID(self):
        """
        If a tag is followed by a PID, the PID is not included.
        """
        line = ("<29>Jan 16 15:08:58 myhost wpa_supplicant[1432]: "
                "wlan0: CTRL-EVENT-SCAN-STARTED ")
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('wpa_supplicant', result['tag'])


    def test_pid(self):
        """
        The optional PID is extracted.
        """
        line = ("<29>Jan 16 15:08:58 myhost wpa_supplicant[1432]: "
                "wlan0: CTRL-EVENT-SCAN-STARTED ")
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('1432', result['pid'])
        self.assertEquals('wlan0: CTRL-EVENT-SCAN-STARTED ',
                          result['message'])


    def test_invalidFormat(self):
        """
        If the log line cannot be parsed, it is returned as the message.
        """
        line = "something"
        result = syslog.parseSyslog(line, self.tz)
        self.assertEquals('something', result['message'])
