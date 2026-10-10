# Experimental non-USB PoC

Install only on aarch64. Version 0.1.8 downloads HP's official ULD archive during
image build:
https://ftp.hp.com/pub/softlib/software13/printers/MFP170/uld-hp_V1.00.39.12_00.15.tar.gz

The build verifies SHA256
`cebb9b7b6125e7406634bb9c2a98b01477d1e11d66c7c90474669de9927bc91d`
and stages only the AArch64 `rastertospl`, `libscmssc.so`, HP 15x PPD and
`cms/15xsc.cts` at `/hp-driver`, plus the English EULA at
`/usr/share/doc/hp150-uld/eula.txt`. Review HP's license before use or image
redistribution. No proprietary files are in Git; no manual upload is required.
Architecture mismatch, hash mismatch or driver validation failure stops the build.
The existing validator runs again before PAPPL starts.

PAPPL is intended/configured on container TCP 8631, published by HAOS on host
TCP 8631 (`8631/tcp: 8631`). Open `http://<HAOS-IP>:8631/`. Web UI and watchdog
use `[PORT:8631]`. After updating from 0.1.4, check Configuration → Network maps
`8631/tcp` to `8631`. Docker examples publish `8631:8631`. There is no ingress.

The user confirmed deployed HAOS 0.1.3 was reachable at
`http://192.168.0.3:8631/` and showed the PAPPL/CUPS page, although PAPPL logged
`:863`. Version 0.1.4 incorrectly treated that log as a mapping failure;
0.1.5 restored the known-good 0.1.3 ports and entrypoint validation semantics.
Reviewed retrofit/PAPPL/CUPS sources preserve 8631 and do not prove the cause.
The discrepancy remains diagnostic; no speculative upstream fix is applied.
Startup logs the effective validated POC_PORT and each exact server exec argument
without dumping secrets or the environment. Rebuild on ARM64 and verify these
lines, full listener logs, host reachability, Web UI and watchdog on HAOS; collect
the actual image/package manifest if the discrepancy persists. Capture conversion
still needs runtime testing. See README for source links and validation limits.

`Unable to initialize DNS-SD: Daemon not running` is still expected because no
Avahi daemon runs. The observed service continued to listen; discovery is a
later issue, separate from direct HTTP reachability. Use only
the `cups:capture:/hp150` queue: the app has no USB access and cannot print to
the connected printer. The TCP watchdog checks reachability only. Startup is
manual. `/work` is container-local experimental state; export captures before
rebuilds or removal.

## Security fix in 0.1.6

HAOS 0.1.5 runtime evidence showed that PAPPL/retrofit external-backend debug
logging exposed inherited environment variables, including Supervisor bearer
tokens. Startup now unsets `SUPERVISOR_TOKEN` and `HASSIO_TOKEN` before every
`legacy-printer-app` launch (server and driver enumeration), so its filters and
backends cannot inherit either token. The PoC needs no Supervisor/Core API access.
Debug logging remains enabled; PATH, TZ, POC_PORT and all state, spool, capture,
filter, backend and library settings remain available. No other environment
variables are removed because their contents and functional requirements are
not established here; do not inject additional credentials into this PoC.

The regression harness stubs driver preparation only, executes the actual shell
launch logic with synthetic token markers, and checks both the app and a spawned
child for token absence and required variables. It also verifies exact server
arguments, including `server-port=8631`, and driver-listing mode. HP ULD staging,
8631 publication and the unexplained PAPPL `:863` diagnostic remain unchanged.

Treat logs collected from 0.1.5 as sensitive. Remove exposed credentials from
shared copies and replace any exposed bearer credentials through the appropriate
HAOS credential lifecycle. This fix prevents inheritance on entrypoint launches;
manual `docker exec ... legacy-printer-app` bypasses the entrypoint, so sanitize
both token variables explicitly for manual commands. Debug logs and captures can
still contain job metadata or document content. ARM64 image rebuild and HAOS
runtime verification of 0.1.6 remain required.

The working `Deluka-BE/haos-cups-hp150` CUPS 2.4 release is separate and untouched.
See the [repository README](https://github.com/Deluka-BE/haos-cups3-hp150-poc#readme)
for installation, staging, capture testing and current validation limits.

## Capture conversion in 0.1.7

Create `hp150-capture` in the PAPPL web UI with `cups:capture:/hp150` and the
HP Color Laser 15x Series driver. Use its **Print Test Page** action, wait for
completion, and match the job id to the filter and capture diagnostics.
Output is `/work/capture/job-<id>-<unique>.spl` with `.spl.json` containing UTC
time, job id, size and SHA-256. Version 0.1.8 automatically checks each completed capture and logs one PASS/FAIL
line with job id, byte count, SHA-256 and fixed format/signature labels. A failure
returns backend failure and retains the evidence. The optional manual
`/opt/poc/scripts/verify-capture.py` uses the same logic. PASS checks metadata
integrity and a stream-start PJL QPDL declaration; it does not validate QPDL
page records, stream completeness or printer acceptance. No document bytes,
paths, titles, options or environment are logged by the verifier. Export evidence before
updates; `/work` remains container-local. See README for commands and acceptance.

The backend receives the final PPD-filter stream; no architecture change was
needed. The CMS layout now follows the vendor's CUPS_DATADIR lookup under
`/work/share/cups/model/uld-hp/cms/15xsc.cts`. A filter wrapper preserves the
normal PPD chain and invokes the real ULD binary with fixed lookup settings.
Startup checks component permissions, directory writes and library loading.
The backend handles CUPS side-channel capability/status requests for the virtual
sink and avoids empty captures from administrative opens. No USB/device access
is enabled. Tests prove scaffolding locally; full ARM64/HAOS conversion and CMS
initialization still require runtime verification.

The 0.1.7 HAOS ARM64 capture path is user-confirmed. Rebuild 0.1.8 and verify
automatic PASS reporting for a normal test page, retained evidence on verifier
failure, job status and continued host Web UI access on 8631. USB stays disabled.
