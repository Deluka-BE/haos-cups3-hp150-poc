#!/bin/sh
set -eu
# Fixed internal port: HAOS publishes host 8631 -> container 863.
# Reject overrides that would silently disagree with config.yaml/EXPOSE.
POC_PORT=${POC_PORT-863}
[ "$POC_PORT" = 863 ] || { echo 'Invalid POC_PORT: internal port must be 863' >&2; exit 1; }
python3 /opt/poc/scripts/validate-driver.py /hp-driver
mkdir -p /work/state/ppd /work/spool /work/capture /work/filter /work/lib
cp /hp-driver/HP_Color_Laser_15x_Series.ppd /work/state/ppd/
cp /hp-driver/rastertospl /work/filter/
chmod 755 /work/filter/rastertospl
cp /hp-driver/libscmssc.so /work/lib/
mkdir -p /work/filter/cms
cp /hp-driver/cms/15xsc.cts /work/filter/cms/
export LD_LIBRARY_PATH=/work/lib
export PPD_DIRS=/work/state/ppd USER_PPD_DIR=/work/state/ppd
export FILTER_DIR=/work/filter BACKEND_DIR=/opt/poc/backend
export STATE_DIR=/work/state SPOOL_DIR=/work/spool CAPTURE_DIR=/work/capture
# Working directory is also isolated; ULD CMS lookup location needs runtime confirmation.
cd /work/filter
case "${1:-server}" in
    validate) exit 0 ;;
    drivers) exec legacy-printer-app drivers ;;
    server) echo "Starting PAPPL on 0.0.0.0:$POC_PORT (HAOS default host port 8631)"
        exec legacy-printer-app server -o "server-port=$POC_PORT" \
        -o listen-hostname=0.0.0.0 -o log-file=- -o log-level=debug ;;
    *) echo 'Allowed modes: server, drivers, validate' >&2; exit 1 ;;
esac
