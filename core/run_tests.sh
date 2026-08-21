#!/bin/bash

# Set the Django settings module for testing
export DJANGO_SETTINGS_MODULE=sterna.settings.test

# Change to the core directory
cd "$(dirname "$0")"

# Run pytest with all arguments passed to this script
python3 -m pytest "$@"