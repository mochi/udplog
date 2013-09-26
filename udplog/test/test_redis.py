# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Tests for L{udplog.redis}.
"""

from __future__ import division, absolute_import

import simplejson

from twisted.application.internet import TCPClient
from twisted.internet import defer
from twisted.trial import unittest

from udplog import redis
from udplog.twisted import DispatcherFromUDPLogProtocol

class FakeRedisClient(object):

    def __init__(self):
        self.pushes = []
        self.disconnected = False


    def lpush(self, key, *values, **kwargs):
        if self.disconnected:
            return defer.fail(RuntimeError("Not connected"))
        else:
            self.pushes.append((key, values, kwargs))
            return defer.succeed(len(self.pushes))


class RedisPublisherServiceTest(unittest.TestCase):

    def setUp(self):
        self.dispatcher = DispatcherFromUDPLogProtocol()
        self.client = FakeRedisClient()
        self.publisher = redis.RedisPublisher(self.dispatcher,
                                              self.client,
                                              "test_list")


    def test_startService(self):
        """
        The publisher registers itself with the dispatcher.
        """
        event = {'message': 'test'}

        self.dispatcher.eventReceived(event)
        self.assertEqual(0, len(self.client.pushes))

        self.publisher.startService()

        self.dispatcher.eventReceived(event)
        self.assertEqual(1, len(self.client.pushes))


    def test_stopService(self):
        """
        The publisher registers itself with the dispatcher.
        """
        event = {'message': 'test'}

        self.publisher.startService()
        self.dispatcher.eventReceived(event)

        self.publisher.stopService()

        self.dispatcher.eventReceived(event)
        self.assertEqual(1, len(self.client.pushes))


    def test_sendEvent(self):
        """
        An event is pushed as a JSON string.
        """
        event = {'category': u'test',
                 'message': u'test',
                 'timestamp': 1340634165}
        self.publisher.sendEvent(event)

        output = self.client.pushes[-1]
        self.assertEqual('test_list', output[0])
        eventDict = simplejson.loads(output[1][0])
        self.assertEqual(u'test', eventDict['message'])


    def test_sendEventUnserializable(self):
        """
        An event that cannot be serialized is dropped and an error logged.
        """
        class Object(object):
            pass

        event = {'category': u'test',
                 'message': Object(),
                 'timestamp': 1340634165}
        self.publisher.sendEvent(event)

        self.assertEqual(0, len(self.client.pushes))
        self.assertEqual(1, len(self.flushLoggedErrors(TypeError)))


    def test_sendEventNoClient(self):
        """
        An event that cannot be serialized is dropped and an error logged.
        """
        event = {'category': u'test',
                 'message': u'test',
                 'timestamp': 1340634165}

        def lpush(key, *args, **kwargs):
            return defer.fail(redis.NoClientError())

        self.patch(self.client, "lpush", lpush)

        self.publisher.sendEvent(event)

        self.assertEqual(0, len(self.client.pushes))
        self.assertEqual(0, len(self.flushLoggedErrors()),
                         "Unexpected error logged")



class FakeFactory(object):

    def __init__(self, client):
        self.client = client

        self.deferred = defer.Deferred()

        if client is not None:
            self.deferred.callback(client)


    def disconnect(self):
        self.client.disconnected = True
        self.deferred = defer.Deferred()



class RedisPushMultiClientTest(unittest.TestCase):

    def test_lpush(self):
        """
        An lpush is passed on to the factory client.
        """
        client = FakeRedisClient()
        factories = [FakeFactory(client)]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        def cb(result):
            self.assertEqual(1, result)
            output = client.pushes[-1]
            self.assertEqual('test_list', output[0])
            self.assertEqual(value, output[1][0])

        d = multiClient.lpush('test_list', value)
        d.addCallback(cb)
        return d


    def test_lpushNoFactories(self):
        """
        If the list of factories is empty, NoClientError is raised.
        """
        factories = []
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        d = multiClient.lpush('test_list', value)
        self.assertFailure(d, redis.NoClientError)
        return d


    def test_lpushNoClient(self):
        """
        If a factory's client is not connected, it is removed from the pool.
        """
        factories = [FakeFactory(None)]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        d = multiClient.lpush('test_list', value)
        self.assertFailure(d, redis.NoClientError)
        return d


    def test_lpushRuntimeError(self):
        """
        If the list of factories is empty, NoClientError is raised.
        """
        client = FakeRedisClient()
        factories = [FakeFactory(client)]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        def lpush(key, *args, **kwargs):
            return defer.fail(RuntimeError("something"))

        self.patch(client, "lpush", lpush)
        d = multiClient.lpush('test_list', value)
        self.assertFailure(d, RuntimeError)
        return d


    def test_lpushMultiple(self):
        """
        Pushes are distributed over multiple clients.
        """
        client1 = FakeRedisClient()
        client2 = FakeRedisClient()
        factories = [FakeFactory(client1), FakeFactory(client2)]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        def cb(result):
            self.assertNotEqual(0, len(client1.pushes), "No pushes to client1")
            self.assertNotEqual(0, len(client2.pushes), "No pushes to client2")
            self.assertEqual(50, len(client1.pushes) + len(client2.pushes))

        d = defer.gatherResults([multiClient.lpush('test_list', value)
                                 for i in xrange(50)])
        d.addCallback(cb)
        return d


    def test_lpushMultipleOneDisconnected(self):
        """
        If a client is disconnected, its factory is removed from the pool.
        """
        client1 = FakeRedisClient()
        factory1 = FakeFactory(client1)
        client2 = FakeRedisClient()
        factory2 = FakeFactory(client2)
        factories = [factory1, factory2]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        def cb(result):
            self.assertNotIn(factory1, multiClient.factories)
            self.assertEqual(0, len(client1.pushes))
            self.assertEqual(50, len(client2.pushes))

        factory1.disconnect()
        d = defer.gatherResults([multiClient.lpush('test_list', value)
                                 for i in xrange(50)])
        d.addCallback(cb)
        return d


    def test_lpushMultipleReconnected(self):
        """
        If a factory reconnects, it is added back to the pool.
        """
        client1 = FakeRedisClient()
        factory1 = FakeFactory(client1)
        client2 = FakeRedisClient()
        factory2 = FakeFactory(client2)
        factories = [factory1, factory2]
        multiClient = redis.RedisPushMultiClient(factories)

        value = '{"message": "test"}'

        def onDisconnected(result):
            self.assertNotIn(factory1, multiClient.factories)
            self.assertEqual(0, len(client1.pushes))
            self.assertEqual(50, len(client2.pushes))

            client1.disconnected = False
            factory1.deferred.callback(client1)
            self.assertIn(factory1, multiClient.factories)

        factory1.disconnect()
        d = defer.gatherResults([multiClient.lpush('test_list', value)
                                 for i in xrange(50)])
        d.addCallback(onDisconnected)
        return d


class MakeServiceTest(unittest.TestCase):
    """
    Tests for L{redis.makeService}.
    """

    def test_services(self):
        """
        The right type and number of services are created.
        """
        config = {'redis-hosts': set(['10.0.0.2', '10.0.0.3']),
                  'redis-port': 6379,
                  'redis-key': 'udplog'}
        dispatcher = DispatcherFromUDPLogProtocol()
        multiService = redis.makeService(config, dispatcher)
        services = list(multiService)

        self.assertEqual(3, len(services))

        for service in services[:-1]:
            self.assertIsInstance(service, TCPClient)

        self.assertIsInstance(services[-1], redis.RedisPublisher)
