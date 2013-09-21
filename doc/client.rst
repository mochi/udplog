Python Client support
=====================

Using the UDPLog client directly
--------------------------------

The Python UDPLog client is in :api:`udplog.udplog`. Use like
so:

.. code-block:: python

   from udplog import udplog
   logger = udplog.UDPLogger()
   logger.log('some_category', {'a_key': 'a_value', 'another_key': 17})

The dictionary passed as the second arg must be safe for JSON encoding.


Using the Python logging facility
---------------------------------

This is the preferred method when the log events should also appear in local
log files. Every Python source file will add this at the top:

.. code-block:: python

  import logging

  logger = logging.getLogger(__name__)

This will set up a local logger that carries the module path as the logger
name.  

Then, ``logger`` is a :py:class:`logging.Logger` on which you can call methods
like :py:meth:`~logging.Logger.debug`, :py:meth:`~logging.Logger.info` and
:py:meth:`~logging.Logger.error`:

.. code-block:: python

  logger.info("Function %(func)s took %(time_elapsed)s",
              {'func': func,
               'time_elapsed': time.time() - start_time})

The logged message will be passed through the Python logging facility, to be
delivered to log handlers. Using a format string and a dictionary with values,
instead of a pre-formatted log message, makes those values individually
available to the log handlers. For :api:`udplog.udplog.UDPLogHandler
<UDPLogHandler>`,
explained below, those values become available as keys in the JSON sent out.
Then, when the log events are sent on to Logstash, they appear as fields that
can be used for filtering and queries.

When an exception occurs that needs to be logged, you can use
:py:meth:`~logging.Logger.exception` from an exception handler. This will allow
log handlers to add tracebacks to the logged entries. In this case,
:api:`udplog.udplog.UDPLogHandler<UDPLogHandler>` will add three fields to the
log event: ``excText``, ``excType`` and ``excValue``. Respectively, they hold
the rendered traceback, the exception type and the exception value (usually the
arguments passed to the exception when raised):

.. code-block:: python

  a = {}
  try:
      b = a['foo']
  except:
      log.exception("Oops, no %(bar)s", {'bar': 'foo'})

:api:`udplog.udplog.UDPLogHandler<UDPLogHandler>` further adds fields for the
filename and the line number where the log event was created (``filename`` and
``lineno``), as well as the function name (``funcName``) and the log level and
logger name (``logLevel`` and ``logName``).

The log handler usually only has to be setup once per application, for example
in the application's ``main`` function:

.. code-block:: python

  logging.basicConfig()
  root = logging.getLogger()
  root.setLevel(logger.INFO)
  root.addHandler(udplog.UDPLogHandler(UDPLogger(), 'python_logging'))

This will set up default logging to ``stderr``, set the minimum log level to
``INFO`` and then add a handler for logging to UDPLog. The second argument
passed to the handler is the UDPLog category. You can override this on
individual log events by adding a ``category`` field in the dictionary passed
as the second argument to the log methods.

The handler also supports the ``extra`` keyword argument to the logger methods,
adding the values to the emitted dictionary. The logging module has the very
useful :py:class:`~logging.LoggerAdapter` to wrap a regular logger to add extra
data to every log event.

A complete `Python logging example <examples/python_logging.py>`_:

.. literalinclude:: examples/python_logging.py
    :language: python
    :linenos:

The call to :py:meth:`~logging.Logger.exception` results in this event
dictionary:

.. code-block:: json

  {
    "appname": "example",
    "category": "python_logging",
    "excText": "Traceback (most recent call last):\n
                  File \"doc/examples/python_logging.py\", line 39, in main\n
                    print a['something']\n
                KeyError: 'something'",
    "excType": "exceptions.KeyError",
    "excValue": "'something'",
    "filename": "doc/examples/python_logging.py",
    "funcName": "main",
    "hostname": "localhost",
    "lineno": 41,
    "logLevel": "ERROR",
    "logName": "__main__",
    "message": "Oops!",
    "timestamp": 1379508311.437895
  }


Using the Twisted logging system
--------------------------------

Twisted has its own logging system in :api:`twisted.python.log` and
:api:`udplog.twisted.UDPLogObserver` can be set up to send all logged events
onto a UDPLog server. It has special support for rendering exceptions and
warnings. See :api:`udplog.twisted.UDPLogObserver.emit<UDPLogObserver.emit>`
for details.

The following `Twisted logging example <examples/twisted_logging.py>`_ sets up
the log observer and uses the Twisted logging system to emit a few log events:

.. literalinclude:: examples/twisted_logging.py
    :language: python
    :linenos:

The call to :api:`twisted.log.err<log.err>` has ``None`` as the first argument,
so that the most recent exception is retrieved from the execution context.
Alternatively, you can pass an exception instance or
:api:`twisted.python.failure.Failure<failure.Failure>`. The second argument is
the *why* of the log event, and ends up in the ``message`` field of the event
dictionary:

.. code-block:: json

  {
    "category": "twisted_logging",
    "excText": "Traceback (most recent call last):\n
                  File \"doc/examples/twisted_logging.py\", line 34, in <module>\n
                    main()\n
                --- <exception caught here> ---\n
                  File \"doc/examples/twisted_logging.py\", line 28, in main\n
                  print a['something']\nexceptions.KeyError: 'something'\n",
    "excType": "exceptions.KeyError",
    "excValue": "'something'",
    "isError": true,
    "logLevel": "ERROR",
    "message": "Oops!",
    "system": "-",
    "timestamp": 1379507871.564469
  }

The warning is rendered as follows:

.. code-block:: json

  {
    "category": "twisted_logging",
    "filename": "doc/examples/twisted_logging.py",
    "isError": false,
    "lineno": 34,
    "logLevel": "WARNING",
    "message": "Don't do foo, do bar instead!",
    "system": "-",
    "timestamp": 1379507871.564662,
    "warningCategory": "exceptions.UserWarning"
  }
