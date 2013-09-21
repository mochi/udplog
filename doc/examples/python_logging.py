"""
Example of using the standard logging facility to send events to udplog.
"""

import logging
import socket
import warnings

from udplog.udplog import UDPLogger, UDPLogHandler

# Get a logger in the idiomatic way.
logger = logging.getLogger(__name__)

# Set up logging to stdout
logging.basicConfig(level=logging.DEBUG)

# Capture warnings, too.
logging.captureWarnings(True)

# Add the UDPLog handler to the root logger.
udplogger = UDPLogger(defaultFields={
                          'appname': 'example',
                          'hostname': socket.gethostname(),
                          })
root = logging.getLogger()
root.setLevel(logging.DEBUG)
root.addHandler(UDPLogHandler(udplogger, category="python_logging"))

def main():
    logger.debug("Starting!")
    logger.info("This is a simple message")
    logger.info("This is a message with %(what)s", {'what': 'variables'})

    extra_logger = logging.LoggerAdapter(logger, {'bonus': 'extra data'})
    extra_logger.info("Bonus ahead!")

    a = {}
    try:
        print a['something']
    except:
        logger.exception("Oops!")

    warnings.warn("Don't do foo, do bar instead!", stacklevel=2)

main()
