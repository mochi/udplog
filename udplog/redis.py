# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Redis support.

This provides a Twisted based publisher to a named list on one or more Redis
servers.
"""

from __future__ import division, absolute_import

import random

import simplejson

from twisted.application import internet, service
from twisted.python import log
from twisted.internet import defer

from txredis.client import RedisClientFactory

class NoClientError(Exception):
    """
    Raised when there are no connected clients.
    """



class RedisPublisher(service.Service):
    """
    Publisher that pushes events to a Redis list.
    """

    def __init__(self, dispatcher, client, key):
        self.dispatcher = dispatcher
        self.client = client
        self.key = key


    def startService(self):
        service.Service.startService(self)
        self.dispatcher.register(self.sendEvent)


    def stopService(self):
        self.dispatcher.unregister(self.sendEvent)
        service.Service.startService(self)


    def sendEvent(self, event):
        try:
            value = simplejson.dumps(event)
        except (TypeError, ValueError):
            log.err(None, "Could not encode event to JSON")
            return

        try:
            d = self.client.lpush(self.key, value)
        except:
            log.err()
        d.addErrback(lambda failure: failure.trap(NoClientError))
        d.addErrback(log.err)



class RedisPushMultiClient(object):
    """
    Redis push client for round-robin dispatch to multiple clients.

    This takes a list of client factories that are selected at random
    to dispatch each single push. If a client is not (yet) connected, the
    factory is taken out of the list of candidates, and re-added when
    the a new connection has been made.
    """

    def __init__(self, factories):
        """
        Initialize.

        @param factories: Client factories.
        @type factories: C{list} of L{RedisClientFactory}.
        """
        self.factories = set(factories)


    def _reconnected(self, factory):
        """
        Called when a new connection for this factory has been made.
        """
        self.factories.add(factory)


    def _disconnected(self, factory):
        """
        Called when the connection for this factory is gone.
        """
        self.factories.remove(factory)
        factory.deferred.addCallback(lambda _: self._reconnected(factory))


    def lpush(self, key, *values, **kwargs):
        """
        Add string to head of list.

        This selects a factory and attempts a push there, falling back to
        others until none are left. In that case, L{NoClientError} is fired
        from the returned deferred.

        @param key: List key
        @param values: Sequence of values to push
        @param value: For backwards compatibility, a single value.
        """
        def eb(failure):
            failure.trap(RuntimeError)
            if failure.value.args == ("Not connected",):
                self._disconnected(factory)
                return self.lpush(key, *values, **kwargs)
            else:
                return failure

        if not self.factories:
            return defer.fail(NoClientError())

        factory = random.sample(self.factories, 1)[0]
        try:
            d = factory.client.lpush(key, *values, **kwargs)
        except AttributeError:
            self._disconnected(factory)
            return self.lpush(key, *values, **kwargs)
        d.addErrback(eb)
        return d


def makeService(config, dispatcher):
    """
    Set up Redis client services.
    """
    s = service.MultiService()

    factories = []

    for host in config['redis-hosts']:
        factory = RedisClientFactory()
        factories.append(factory)
        tcpClient = internet.TCPClient(host,
                                       config['redis-port'],
                                       factory)
        tcpClient.setServiceParent(s)

    client = RedisPushMultiClient(factories)

    publisher = RedisPublisher(dispatcher, client, config['redis-key'])
    publisher.setServiceParent(s)

    return s
