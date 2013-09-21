UDPLog documentation
====================

UDPLog is a system for emitting application log events via UDP and shipping
them via RabbitMQ or Scribe for further processing. The idea is that the
applications sends its structured log events to a dedicated shipping daemon on
the same machine, which in turn passes it on to one or more remote services. As
this uses UDP, emitting events is non-blocking fire-and-forget. A system like
Logstash can then be used to process and store log events.


.. WARNING::

    The U in UDPLog stands for **unreliable**, and that's just what it is. Log
    messages are delivered on a best-effort basis and are not guaranteed in
    any way, even though the default mode is to send logs to a daemon running
    on the same machine.

    Do **not** use UDPLog for any data that must be reliable, such as any
    information used for billing of any sort!

Contents:

.. toctree::
    :maxdepth: 2

    client
    examples/index



Protocol
--------

A log event a combination of a category identifier (ASCII, matching the regular
expression ``^[0-9A-Za-z_]+$``) and a set of name/value pairs. The UDP wire
protocol represents an event as a single datagram composed of the the category,
a colon character, an optional whitespace character and the name/value pairs
rendered as a JSON object::

  some_category: {"a_key": "a_value", timestamp: "1379002018.000"}


What to log and what to call it
-------------------------------

Log everything. It's better to over-log than under-log.

In general, it is better to have to fewer distinct categories, and to have
multiple types of entries in the same category if they have common fields.
Using ElasticSearch and Logstash, you can then define a mapping for each
category. To distinguish the events in the same category, you can add another
field like ``event``.

In general, an application shouldn't have more than a few categories, and
categories can span multiple applications.

The UDPLog libraries already adds a timestamp to each event. You do not need to
add a timestamp to your logs, unless you want to record the exact time your
event happened as opposed to the time the log was created. In that case, set
the ``timestamp`` field.

All times should be expressed in seconds, not micro or milliseconds. Generally,
you'll want a floating point number of seconds. Timestamps are expressed as
floating point seconds since the UNIX epoch.


Emitting log events
-------------------

There are a several ways to emit log events from applications:

 * With direct calls to the logger.
 * Via the Python logging facility.
 * Via the Twisted logging system.

See :doc:`client <client>` for details.


Receiving log events
--------------------

To ship log events to Scribe and/or RabbitMQ, there is Twisted-based support
for receiving UDPLog events and passing them to those systems. This is exposed
via a ``twistd`` plugin called ``udplog``.

Pass all events to a local Scribe service::

    twistd udplog --scribe-host=localhost


Pass all events to a RabbitMQ server, using the exchange named `logs`::

    twistd udplog --rabbitmq-host=10.0.0.2 --rabbitmq-exchange=logs


For a full list of command line options, run::

    twistd udplog --help


Testing
-------

To capture logs during application development, run a UDPLog daemon. This will
print to the console all messages it receives::

    python -mudplog.udplog

Or, using the ``twistd`` plugin::

    twistd -n udplog --verbose


Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
