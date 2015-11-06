# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Kafka support.

This provides a Twisted based publisher to a topic in a Kafka cluster.
"""
from __future__ import division, absolute_import

import socket

from kafka import KafkaClient, SimpleProducer
import simplejson
from twisted.application import service

class KafkaPublisher(service.Service):
    """
    Publisher that pushes events to a Kafka cluster.
    """

    def __init__(self, dispatcher, producer, topic):
        self._dispatcher = dispatcher
        self._producer = producer
        self._topic = topic


    def startService(self):
        service.Service.startService(self)
        self._dispatcher.register(self._sendEvent)


    def stopService(self):
        self._dispatcher.unregister(self._sendEvent)
        self._producer.stop()
        service.Service.stopService(self)


    def _sendEvent(self, event):
        encoded = simplejson.dumps(event).encode('utf-8')
        self._producer.send_messages(self._topic, encoded)


def makeService(config, dispatcher):
    client_id = 'udplog-{}'.format(socket.getfqdn())
    client = KafkaClient(config['kafka-brokers'], client_id)
    producer = SimpleProducer(
        client,
        async=True,
        async_queue_maxsize=config['kafka-buffer-maxsize'],
        batch_send_every_n=config['kafka-send-every-msg'],
        batch_send_every_t=config['kafka-send-every-sec'])

    return KafkaPublisher(dispatcher, producer, config['kafka-topic'])
