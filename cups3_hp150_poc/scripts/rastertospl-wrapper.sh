#!/bin/sh
# Keep the PPD's normal filter name; exec preserves stdin/stdout and exit status.
set -eu
unset SUPERVISOR_TOKEN HASSIO_TOKEN
export LD_LIBRARY_PATH=/work/lib
export CUPS_DATADIR=/work/share/cups
[ -r "${PPD:?PPD required}" ]
[ -x /work/filter/rastertospl.real ]
[ -r /work/lib/libscmssc.so ]
[ -s /work/share/cups/model/uld-hp/cms/15xsc.cts ]
printf '%s\n' 'INFO: HP150 invoking /work/filter/rastertospl.real; library=/work/lib/libscmssc.so; CMS=/work/share/cups/model/uld-hp/cms/15xsc.cts' >&2
exec /work/filter/rastertospl.real "$@"
