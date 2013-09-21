UDPLog
======

What is this?
-------------

UDPLog is a system for emitting application log events via UDP and shipping
them via RabbitMQ or Scribe for further processing. The idea is that the
applications sends its structured log events to a dedicated shipping daemon on
the same machine, which in turn passes it on to one or more remote services. As
this uses UDP, emitting events is non-blocking fire-and-forget. An application
like Logstash can then be used to process and store log events.


Requirements
------------

 - simplejson
 - Twisted (optional for Twisted logging support and requisite for the
   server-side shippers)
 - txAMQP (for shipping to RabbitMQ)
 - scribe (for shipping to Scribe)
 - thrift (for shipping to Scribe)

To generate the documentation:

 - docutils
 - Sphinx
 - pydoctor (including apilinks_sphinxext.py)
 - epydoc


Copyright and Warranty
----------------------

The code in this distribution started as an internal tool at Mochi Media and is
made available under the MIT License. See the included LICENSE file for details.
