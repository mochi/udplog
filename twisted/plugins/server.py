# Copyright (c) Mochi Media, Inc.
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Twisted Plugins for udplog services.
"""

from __future__ import division, absolute_import

from twisted.application.service import ServiceMaker

UDPLogServer = ServiceMaker(
    "UDPLog Server",
    "udplog.tap",
    "A service that accepts structured logs via UDP and dispatches them to "
        "Scribe or RabbitMQ.",
    "udplog")
