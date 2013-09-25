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

from twisted.python import log
from twisted.internet import defer

class NoClientError(Exception):
    """
    Raised when there are no connected clients.
    """



class RedisPublisher(object):
    """
    Publisher that pushes events to a Redis list.
    """

    def __init__(self, dispatcher, client, key):
        self.dispatcher = dispatcher
        self.client = client
        self.key = key

        self.dispatcher.register(self.sendEvent)


    def sendEvent(self, event):
        try:
            value = simplejson.dumps(event)
        except (TypeError, ValueError):
            log.err(None, "Could not encode event to JSON")
            return

        d = self.client.lpush(self.key, value)
        d.addErrback(lambda failure: failure.trap(NoClientError))
        d.addErrback(log.err)



class RedisPushMultiClient(object):

    def __init__(self, factories):
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
