#!/bin/sh
set -eu
if [ "${1:-server}" = server ]; then
    # Bootstrap supplies only a validated value; never reopen Supervisor options.
    case "${POC_LOG_LEVEL:-}" in
        fatal|error|warn|info|debug) log_level=$POC_LOG_LEVEL ;;
        *) echo 'ERROR: invalid add-on log_level options; refusing server startup' >&2; exit 1 ;;
    esac
fi
case "${POC_PORT:-8631}" in *[!0-9]*|'') echo 'Invalid POC_PORT' >&2; exit 1;; esac
[ "${POC_PORT:-8631}" -ge 1024 ] && [ "${POC_PORT:-8631}" -le 65535 ]
python3 /opt/poc/scripts/validate-driver.py /hp-driver
mkdir -p /work/state/ppd /work/spool /work/capture /work/filter /work/lib
cp /hp-driver/HP_Color_Laser_15x_Series.ppd /work/state/ppd/
cp /hp-driver/rastertospl /work/filter/rastertospl.real
cp /opt/poc/scripts/rastertospl-wrapper.sh /work/filter/rastertospl
chmod 755 /work/filter/rastertospl /work/filter/rastertospl.real
cp /hp-driver/libscmssc.so /work/lib/
mkdir -p /work/share/cups/model/uld-hp/cms
cp /hp-driver/cms/15xsc.cts /work/share/cups/model/uld-hp/cms/
export LD_LIBRARY_PATH=/work/lib
export PPD_DIRS=/work/state/ppd USER_PPD_DIR=/work/state/ppd
export FILTER_DIR=/work/filter BACKEND_DIR=/opt/poc/backend
export STATE_DIR=/data/state SPOOL_DIR=/work/spool CAPTURE_DIR=/work/capture
# ULD uses CUPS_DATADIR/model/uld-<lowercase manufacturer>/cms/<linuxIdentify>.
cd /work/filter
# Retrofit debug logging can expose inherited environment variables.
# This PoC needs neither Supervisor nor Core API credentials.
# Remove both HAOS token aliases before any app launch, including drivers mode;
# filters and backends inherit the sanitized app environment.
unset SUPERVISOR_TOKEN HASSIO_TOKEN
python3 /opt/poc/scripts/state-runtime.py
python3 /opt/poc/scripts/runtime-check.py
case "${1:-server}" in
    validate) exit 0 ;;
    drivers) exec legacy-printer-app drivers ;;
    server) python3 /opt/poc/scripts/usb-diagnostics.py
        python3 /opt/poc/scripts/usb-settle.py
        set -- legacy-printer-app server -o "server-port=${POC_PORT:-8631}" \
        -o server-options=no-tls -o listen-hostname=0.0.0.0 -o log-file=- -o "log-level=$log_level"
        echo "INFO: lifecycle stage=startup version=0.1.25 diagnostics=enabled"
        echo "PAPPL transport: policy=ipp-only uri-security-supported=none tls=disabled port=8631 credentials=not-configured"
        # Log only the validated numeric port and these allowlisted, non-secret arguments.
        printf 'PAPPL launch: POC_PORT=<%s> (effective)\n' "${POC_PORT:-8631}"
        arg_index=0
        for arg do
            printf 'PAPPL launch: argv[%s]=<%s>\n' "$arg_index" "$arg"
            arg_index=$((arg_index + 1))
        done
        exec python3 /opt/poc/scripts/mdns-runtime.py "$@" ;;
    *) echo 'Allowed modes: server, drivers, validate' >&2; exit 1 ;;
esac
