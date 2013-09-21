"""
Example of using the Twisted logging facility to send events to udplog.
"""

import sys
import warnings

from twisted.python import log

from udplog.udplog import UDPLogger
from udplog.twisted import UDPLogObserver

# Set up logging to stdout
log.startLogging(sys.stdout)

# Set up the udplog observer
udplogger = UDPLogger()
observer = UDPLogObserver(udplogger, defaultCategory='twisted_logging')
log.addObserver(observer.emit)

def main():
    log.msg("Starting!")
    log.msg("This is a simple message")
    log.msg(format="This is a message with %(what)s", what='variables')

    a = {}
    try:
        print a['something']
    except:
        log.err(None, "Oops!")

    warnings.warn("Don't do foo, do bar instead!", stacklevel=2)

main()
