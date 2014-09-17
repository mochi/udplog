# Copyright (c) Christopher Zorn.
# See LICENSE for details.

"""
DataDog support.

This provides a Twisted based publisher to datadog API endpoints.
"""
from __future__ import division, absolute_import

import simplejson

from zope.interface import implements

from twisted.application import internet, service
from twisted.python import log
from twisted.internet import defer

from twisted.web.iweb import IBodyProducer

from twisted.web import client as web_client, http_headers

#from dogapi import dog_http_api as datadog

API_URL='https://app.datadoghq.com/api/v1/events'

class DataDogClient(object):
    def __init__(self, api_key, application_key):
        self.api_key = api_key
        self.application_key = application_key

    def send_event(self, event):
        headers = http_headers.Headers(
            {'Content-Type': ['application/json']}),
        d = web_client.Agent(reactor).request(
            'POST',
            API_URL+'?api_key='+self.api_key,
            headers,
            JSONProducer(event))
        return d

class DataDogPublisher(service.Service):
    """
    Publisher that POSTs events to data dog.
    """

    def __init__(self, dispatcher, client):
        self.dispatcher = dispatcher
        self.client = client
        #self.api_key = api_key
        #self.application_key = application_key

    def startService(self):
        service.Service.startService(self)
        self.dispatcher.register(self.sendEvent)


    def stopService(self):
        self.dispatcher.unregister(self.sendEvent)
        service.Service.startService(self)


    def sendEvent(self, event):
        
        try:
            d = self.client.send_event(event)
            d.addErrback(log.err)
        except:
            log.err()


class JSONProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = simplejson.dumps(body)
        self.length = len(self.body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

def makeService(config, dispatcher):
    """
    Set up DataDog client services.
    """
    s = service.MultiService()
    client = DataDogClient(config['dd-api-key'],
                           config['dd-application-key'])
    publisher = DataDogPublisher(dispatcher,
                                 client)
    publisher.setServiceParent(s)

    return s
