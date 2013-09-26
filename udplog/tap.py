# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Twisted Application set up for UDPLog.
"""

from __future__ import division, absolute_import

from twisted.application import service
from twisted.application import internet
from twisted.python import usage

from udplog.twisted import DispatcherFromUDPLogProtocol
from udplog.twisted import UDPLogClientFactory
from udplog.twisted import UDPLogToTwistedLog
from udplog import udplog

class Options(usage.Options):
    optParameters = [
        ('udplog-interface', None, udplog.DEFAULT_HOST, 'UDPLog interface'),
        ('udplog-port', None, udplog.DEFAULT_PORT, 'UDPLog port'),

        ('scribe-host', None, None, 'Scribe Thrift host'),
        ('scribe-port', None, 1463, 'Scribe Thrift port'),

        ('rabbitmq-host', None, None, 'RabbitMQ host'),
        ('rabbitmq-port', None, 5672, 'RabbitMQ host'),
        ('rabbitmq-vhost', None, '/', 'RabbitMQ virtual host'),
        ('rabbitmq-exchange', None, 'logs', 'RabbitMQ exchange'),
        ('rabbitmq-queue-size', None, 2500,
             'Maximum number of log events to buffer for RabbitMQ'),
        ('redis-port', None, 6379, 'Redis port'),
        ('redis-key', None, None, 'Redis list key'),
        ]

    optFlags = [
        ('verbose', 'v', 'Log all incoming messages')
        ]

    def __init__(self):
        super(Options, self).__init__()
        self['redis-hosts'] = set()


    def opt_redis_host(self, host):
        """
        Redis host. Repeat for round-robin dispatching.
        """
        self['redis-hosts'].add(host)



def makeService(config):

    s = service.MultiService()

    # Set up UDP server as the dispatcher.
    dispatcher = DispatcherFromUDPLogProtocol()

    udplogServer = internet.UDPServer(port=config['udplog-port'],
                                      protocol=dispatcher,
                                      interface=config['udplog-interface'],
                                      maxPacketSize=65536)
    udplogServer.setServiceParent(s)

    # Set up Thrift/Scribe client.
    if config['scribe-host']:
        from udplog import scribe
        factory = UDPLogClientFactory(scribe.ScribeProtocol,
                                      dispatcher)
        scribeClient = internet.TCPClient(config['scribe-host'],
                                          config['scribe-port'],
                                          factory)
        scribeClient.setServiceParent(s)

    # Set up RabbitMQ client.
    if config['rabbitmq-host']:
        from udplog import rabbitmq
        factory = UDPLogClientFactory(
            rabbitmq.RabbitMQPublisher, dispatcher,
            vhost=config['rabbitmq-vhost'],
            exchange=config['rabbitmq-exchange'],
            queueSize=config['rabbitmq-queue-size'])
        rabbitmqClient = internet.TCPClient(config['rabbitmq-host'],
                                            config['rabbitmq-port'],
                                            factory)
        rabbitmqClient.setServiceParent(s)

    # Set up Redis client.
    if config['redis-hosts']:
        from udplog import redis
        redisService = redis.makeService(config, dispatcher)
        redisService.setServiceParent(s)

    if config['verbose']:
        UDPLogToTwistedLog(dispatcher)

    return s
