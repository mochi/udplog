# Copyright (c) Christopher Zorn.
# See LICENSE for details.

"""
Tests for L{udplog.datadog}.
"""

from __future__ import division, absolute_import

from twisted.internet import defer
from twisted.trial import unittest

from udplog import datadog
from udplog.twisted import DispatcherFromUDPLogProtocol

class FakeClient(object):

    def __init__(self, api_key, application_key):
        self.api_key = api_key
        self.application_key = application_key
        self.events = []

    def send_event(self, event):
        self.events.append(event)
        return defer.succeed(True)

class DataDogPublisherServiceTest(unittest.TestCase):

    def setUp(self):
        self.dispatcher = DispatcherFromUDPLogProtocol()
        self.client     = FakeClient("test_api_key",
                                     "test_application_key")
        self.publisher  = datadog.DataDogPublisher(self.dispatcher,
                                                   self.client)


    def test_startService(self):
        """
        The publisher registers itself with the dispatcher.
        """
        event = {'message': 'test'}

        self.dispatcher.eventReceived(event)
        self.assertEqual(0, len(self.client.events))

        self.publisher.startService()

        self.dispatcher.eventReceived(event)
        self.assertEqual(1, len(self.client.events))


    def test_stopService(self):
        """
        The publisher registers itself with the dispatcher.
        """
        event = {'message': 'test'}

        self.publisher.startService()
        self.dispatcher.eventReceived(event)

        self.publisher.stopService()

        self.dispatcher.eventReceived(event)
        self.assertEqual(1, len(self.client.events))


    def test_sendEvent(self):
        """
        An event is pushed as a JSON string.
        """

        event = {'category': u'test',
                 'message': u'test',
                 'timestamp': 1340634165}
        self.publisher.sendEvent(event)

        output = self.client.events[-1]
        for key in event.iterkeys():
            self.assertEqual(event[key], output[key])



class MakeServiceTest(unittest.TestCase):
    """
    Tests for L{datadog.makeService}.
    """

    def test_services(self):
        """
        The right type and number of services are created.
        """
        config = {'dd-api-key': 'test_api_key',
                  'dd-application-key': 'udplog'}
        dispatcher = DispatcherFromUDPLogProtocol()
        multiService = datadog.makeService(config, dispatcher)
        services = list(multiService)

        self.assertEqual(1, len(services))

        self.assertIsInstance(services[-1], datadog.DataDogPublisher)
