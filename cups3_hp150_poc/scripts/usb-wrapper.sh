#!/bin/sh
unset SUPERVISOR_TOKEN HASSIO_TOKEN
exec python3 /opt/poc/scripts/job-stage.py usb "$@"
