import os
from setuptools import setup

# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "udplog",
    version = "0.0.1",
    author = "Mochi Media",
    description = ("UDPLog is a system for emitting application log events"
                   " via UDP and shipping them via RabbitMQ or Scribe for "
                   "further processing."),
    license = "MIT",
    keywords = "logging twisted udp scribe",
    url = "https://github.com/mochi/udplog",
    packages=['udplog'],
    long_description=read('README.rst'),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
)
