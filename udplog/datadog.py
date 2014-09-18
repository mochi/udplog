# Copyright (c) Christopher Zorn.
# See LICENSE for details.

"""
DataDog support.

This provides a Twisted based publisher to datadog API endpoints.
"""
from __future__ import division, absolute_import

import simplejson

from zope.interface import implements

from twisted.application import service
from twisted.python import log
from twisted.internet import defer, reactor, protocol

from twisted.web.iweb import IBodyProducer

from twisted.web import client as web_client, http_headers


API_URL='https://app.datadoghq.com/api/v1/events'

class DebugPrinter(protocol.Protocol):
    def __init__(self, finished):
        self.finished = finished
        self.remaining = 1024 * 10

    def dataReceived(self, bytes):
        if self.remaining:
            display = bytes[:self.remaining]
            log.msg('Some data received:' + str(display))
            self.remaining -= len(display)

    def connectionLost(self, reason):
        log.msg('Finished receiving body:'+str(reason.getErrorMessage()))
        self.finished.callback(None)

def cbDebugRequest(response):
    log.msg('Response version:'+str(response.version))
    log.msg('Response code:'+str(response.code))
    log.msg('Response phrase:'+str(response.phrase))
    log.msg('Response headers:'+str(list(response.headers.getAllRawHeaders())))
    finished = defer.Deferred()
    response.deliverBody(DebugPrinter(finished))
    return finished


class DataDogClient(object):
    def __init__(self, api_key, application_key = None, verbose = False):
        self.api_key = api_key
        self.application_key = application_key
        self.verbose = verbose

    def send_event(self, event):
        headers = http_headers.Headers(
            {'Content-Type': ['application/json']})
        url = API_URL+'?api_key='+self.api_key
        if self.application_key:
            url += "&application_key="+self.application_key
        d = web_client.Agent(reactor).request(
            'POST',
            url,
            headers=headers,
            bodyProducer=JSONProducer(event))
        if self.verbose:
            d.addCallback(cbDebugRequest)
        return d

class DataDogPublisher(service.Service):
    """
    Publisher that POSTs events to data dog.
    """

    def __init__(self, dispatcher, client):
        self.dispatcher = dispatcher
        self.client = client


    def startService(self):
        service.Service.startService(self)
        self.dispatcher.register(self.sendEvent)


    def stopService(self):
        self.dispatcher.unregister(self.sendEvent)
        service.Service.startService(self)


    def sendEvent(self, event):
        if not event.has_key('tags'):
            event['tags'] = ''
            for key, value in event.iteritems():
                event['tags'] += key+":"+value+","
            event['tags'] += 'emitter:udplog'
        # title MUST be set
        if not event.has_key('title'):
            event['title'] = event.get('category', 'default')
        # priority should be set
        if not event.has_key('priority'):
            ## TODO - map this to logLevel
            event['priority'] = 'normal'
        # text should be set
        if not event.has_key('text'):
            event['text'] = event.get('message', simplejson.dumps(event))

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
                           config['dd-application-key'],
                           config.get('verbose', False))
    publisher = DataDogPublisher(dispatcher,
                                 client)
    publisher.setServiceParent(s)

    return s
