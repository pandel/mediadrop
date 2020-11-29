#!/bin/bash

virtualenv -p python2 --system-site-packages $HOME/venv/

# Downgrade setuptools to avoid the following error:
# 'the `allow-hosts` option is not supported'.
$HOME/venv/bin/pip install setuptools==41.0.0

$HOME/venv/bin/python2 setup.py develop
$HOME/venv/bin/paster setup-app development.ini
