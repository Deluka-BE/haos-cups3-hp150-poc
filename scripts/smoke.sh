#!/bin/sh
# Run on the host after starting the isolated container; never submits a job.
set -eu
container=${1:-hp150-poc}
port=${POC_PORT:-8631}
curl --fail --silent --show-error "http://127.0.0.1:$port/" >/dev/null
docker exec "$container" /opt/poc/scripts/entrypoint.sh drivers > /tmp/hp150-poc-drivers.txt
cat /tmp/hp150-poc-drivers.txt
if ! grep -Ei 'HP.*(15[0x]|Laser)' /tmp/hp150-poc-drivers.txt; then
    echo 'HP driver not found in runtime driver listing' >&2
    exit 1
fi
echo 'HTTP and PPD enumeration passed; filter execution has NOT been tested.'
