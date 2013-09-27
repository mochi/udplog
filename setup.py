import os
from setuptools import setup

# Make sure 'twisted' doesn't appear in top_level.txt

try:
    from setuptools.command import egg_info
    egg_info.write_toplevel_names
except (ImportError, AttributeError):
    pass
else:
    def _top_level_package(name):
        return name.split('.', 1)[0]

    def _hacked_write_toplevel_names(cmd, basename, filename):
        pkgs = dict.fromkeys(
            [_top_level_package(k)
                for k in cmd.distribution.iter_distribution_names()
                if _top_level_package(k) != "twisted"
            ]
        )
        cmd.write_file("top-level names", filename, '\n'.join(pkgs) + '\n')

    egg_info.write_toplevel_names = _hacked_write_toplevel_names

# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "udplog",
    version = "0.1.0",
    author = "Mochi Media",
    author_email = "dev@mochimedia.com",
    maintainer = "Ralph Meijer",
    maintainer_email = "ralphm@ik.nu",
    description = ("UDPLog is a system for emitting application log events"
                   " via UDP and shipping them via RabbitMQ or Scribe for "
                   "further processing."),
    license = "MIT",
    keywords = "logging twisted udp scribe",
    url = "https://github.com/mochi/udplog",
    packages=[
        'udplog',
        'udplog.test',
        'twisted.plugins',
    ],
    package_data={
        'twisted.plugins': ['twisted/plugins/server.py'],
        'udplog': ['amqp0-9-1.extended.xml'],
    },
    zip_safe=False,
    long_description=read('README.rst'),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
        'simplejson',
        'Twisted >= 13.0.0',
        'txAMQP',
        'txredis',
        'thrift',
        'scribe',
    ],
)
