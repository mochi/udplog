# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Twisted Application set up for UDPLog.
"""

from __future__ import division, absolute_import

import socket

from twisted.application import service
from twisted.application import internet
from twisted.python import usage

from udplog.twisted import Dispatcher, UDPLogProtocol
from udplog.twisted import UDPLogClientFactory
from udplog.twisted import UDPLogToTwistedLog
from udplog import syslog, udplog

class Options(usage.Options):
    optParameters = [
        ('udplog-interface', None, udplog.DEFAULT_HOST, 'UDPLog interface'),
        ('udplog-port', None, udplog.DEFAULT_PORT, 'UDPLog port', int),

        ('scribe-host', None, None, 'Scribe Thrift host'),
        ('scribe-port', None, 1463, 'Scribe Thrift port', int),

        ('rabbitmq-host', None, None, 'RabbitMQ host'),
        ('rabbitmq-port', None, 5672, 'RabbitMQ host', int),
        ('rabbitmq-vhost', None, '/', 'RabbitMQ virtual host'),
        ('rabbitmq-exchange', None, 'logs', 'RabbitMQ exchange'),
        ('rabbitmq-queue-size', None, 2500,
             'Maximum number of log events to buffer for RabbitMQ', int),

        ('redis-port', None, 6379, 'Redis port', int),
        ('redis-key', None, None, 'Redis list key'),

        ('syslog-interface', None, '', 'syslog interface'),
        ('syslog-port', None, None, 'syslog port', int),
        ('syslog-unix-socket', None, None, 'syslog UNIX socket'),
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

    # Set up event dispatcher

    dispatcher = Dispatcher()

    # Set up UDPLog server.
    udplogProtocol = UDPLogProtocol(dispatcher.eventReceived)

    udplogServer = internet.UDPServer(port=config['udplog-port'],
                                      protocol=udplogProtocol,
                                      interface=config['udplog-interface'],
                                      maxPacketSize=65536)
    udplogServer.setServiceParent(s)

    # Set up syslog server
    if (config.get('syslog-port') is not None or
        config.get('syslog-unix-socket') is not None):
        hostname = socket.gethostname()
        hostnames = {
            hostname.split('.')[0]: hostname,
            None: hostname
        }
        syslogProtocol = syslog.SyslogDatagramProtocol(
            dispatcher.eventReceived, hostnames=hostnames)

        if config.get('syslog-unix-socket') is not None:
            syslogServer = internet.UNIXDatagramServer(
                address=config['syslog-unix-socket'],
                protocol=syslogProtocol,
                maxPacketSize=65536)
            syslogServer.setServiceParent(s)
        if config.get('syslog-port') is not None:
            syslogServer = internet.UDPServer(
                port=config['syslog-port'],
                protocol=syslogProtocol,
                interface=config.get('syslog-interface', ''),
                maxPacketSize=65536)
            syslogServer.setServiceParent(s)


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
