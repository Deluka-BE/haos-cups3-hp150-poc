# Experimental USB hardware-test PoC

## USB hardware-test release 0.1.12

Starting from user-confirmed 0.1.11 USB node access and CUPS discovery of
`usb://HP/Color%20Laser%20150?serial=CNB2N32ZJ4`, this release installs the real
Debian CUPS USB executable at `/opt/poc/backend/usb` (root-owned, mode 0755).
The diagnostic path is a symlink to that same executable. Retrofit's exclusive
allowlist is `capture,usb`; its built-in PAPPL transports stay disabled and device
PostScript default queries stay disabled. Retrofit prefixes CUPS device URIs
with `cups:` for selection and strips that prefix when invoking the backend.
The HP ULD filter/CMS/QPDL pipeline and capture verifier are unchanged.

Port 8631, token scrubbing, dynamic supplementary USB GIDs, UID/GID 10001 and
no-new-privileges remain unchanged. Only `usb: true` is requested; there are no
new mounts, privileged mode, device chmod/chown, scheduler or automatic queues/jobs.
Discovery may claim USB interfaces; a manually submitted USB job now sends real
print data. Historical diagnostic sections below describe earlier releases.

HAOS test steps:

1. Export any needed `/work/capture` evidence. Refresh **only** the
   `haos-cups3-hp150-poc` app repository, update/rebuild to **0.1.12**, and verify
   the installed version. Keep Protection mode enabled and `8631/tcp` → `8631`.
   Leave the separate stable app/repository and its queues/settings untouched;
   arrange an idle printer with no concurrent jobs for this hardware test.
2. With the HP connected and powered on, start the PoC. Check bootstrap identity
   and HP node access diagnostics, effective `POC_PORT=<8631>`, and
   `PAPPL allowlist=capture,usb`. Both `cups-usb` and `pappl-capture-usb`
   discovery should report the HP URI (the latter with `cups:`). Discovery
   timeout/missing URI is a failed or inconclusive test, not successful transport.
3. Open `http://<HAOS-IP>:8631/` → **Add Printer**. Confirm both the capture
   device `cups:capture:/hp150` and HP Color Laser 150 USB device appear.
   Its PAPPL URI must be
   `cups:usb://HP/Color%20Laser%20150?serial=CNB2N32ZJ4`.
   If either is missing, collect sanitized diagnostic lines and stop before printing.
4. Keep/create `hp150-capture`, selecting the capture URI and **HP Color Laser
   15x Series** driver. Manually use **Print Test Page**, confirm job completion,
   the automatic QPDL `PASS` and `.spl`/`.spl.json` evidence. No physical output
   should result from this capture queue.
5. Manually create a **separate** `hp150-usb-test` queue with the HP USB device
   and **HP Color Laser 15x Series** driver. Verify its URI and driver before
   submission. Creation alone must not print. Manually submit **one Print Test
   Page** to that queue, then inspect job status and the actual page for readable
   content, colors and errors. Capture PASS alone cannot prove USB acceptance.
6. Record version, both selected URIs, sanitized startup/filter/backend diagnostics,
   job status and physical page result. If the job stalls/fails, cancel it and
   stop the PoC before retrying; do not grant privileges or change node permissions.
   URI serial numbers and job logs may identify devices/documents; redact when sharing.

Validation: all 29 unit tests, repository safety/version checks, Python compilation,
shell syntax and diff whitespace checks pass. The Dockerfile source patch also
applies successfully to the pinned retrofit revision.

Static checks validate wiring and regressions only. No ARM64 image build,
HAOS startup, Add Printer interaction or physical printing is claimed locally.



Install only on aarch64. Version 0.1.10 downloads HP's official ULD archive during
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
later issue, separate from direct HTTP reachability. Use the capture and separate manual USB test queues described above. The TCP watchdog checks reachability only. Startup is
manual. `/work` is container-local experimental state; export captures before
rebuilds or removal.

## USB blocker diagnostics (0.1.10; historical)

HAOS 0.1.9 evidence establishes that USB enumeration sees `03f0:ea2a`, but
CUPS discovery reports no accepted HP 150 URI. It does **not** establish the
hardware failure's exact cause. The confirmed diagnostic defect was discarding
CUPS stderr while interpreting its discovery exit status as success: CUPS
returns zero after listing even when libusb initialization/open/claim fails.
The application runs as UID 10001; parent-directory access and `lsusb` do not
prove read/write access to the HP usbfs character device. Permissions/device
cgroup denial is a hypothesis, not a confirmed HAOS finding.

Version 0.1.10 retains the isolated Debian CUPS USB backend, capture-only PAPPL
allowlist, filter pipeline and automatic QPDL verifier. It adds:

- An open/close-only `O_RDWR` check on enumerated `03f0:ea2a` character devices,
  reporting numeric owner/group/mode, current UID, read/write checks and errno.
  This performs no read, write or ioctl. `EACCES` suggests Unix permissions;
  `EPERM` can indicate device cgroup/security policy. Neither warrants privileges
  or broad mounts without further evidence.
- Bounded sysfs HP interface class/subclass/protocol and a fixed driver label.
  Standard CUPS accepts printer class `07`, subclass `01`, protocol `01` or `02`
  with a bulk OUT endpoint, subject to quirks. These sysfs values reflect current
  interfaces, not every alternate setting or the endpoint descriptors.
- Sanitized CUPS stderr evidence: libusb device count, quirks count, numeric
  initialization/open/descriptor errors and fixed HP detach/claim/driver-check
  labels. No raw stderr or USB strings are logged. Open-error codes are not
  device-specific; correlate with the independent HP node check.

The [CUPS USB implementation](https://github.com/OpenPrinting/cups/blob/v2.4.10/backend/usb-libusb.c)
opens devices read/write and may detach kernel drivers, claim interfaces, change
configuration/alternate settings and read identity during discovery. Therefore
this is **discovery-only, not strictly read-only**. It sends no print job; this
corrects the 0.1.9 documentation. No print queue, print backend or access grant
is added. USB printing remains disabled because real device access, discovery
and transport behavior have not been validated on HAOS.

Each subprocess receives a credential-free environment, an eight-second deadline
and a 32-KiB combined output cap for CUPS (stdout-only for other probes). Only
anchored recognized stderr patterns and validated matching HP URIs are emitted.
Diagnostics remain nonfatal. Discovery `status=ok` means subprocess exit zero,
not device access success; `not-reported` means no accepted matching URI.

HAOS validation:

1. Refresh the isolated PoC repository, rebuild/update to **0.1.10**, then start
   with the HP connected. Do not change the production `haos-cups-hp150` app.
2. Collect only `USB diagnostics:` lines, especially `HP-node`, `HP-interface`,
   `cups-usb evidence`, status and visibility. Do not paste environment dumps or
   raw backend output. PAPPL should still report no physical HP URI.
3. If HP `open-rw` fails, resolve that exact node's Unix/device-policy access
   before considering backend changes. If it succeeds, use CUPS evidence to
   distinguish initialization, interface driver/claim problems and URI matching.
   Libusb open code `-3` is access denied; `-4` is disconnected; `-6` is busy.
4. Repeat the proven `cups:capture:/hp150` print and confirm automatic QPDL PASS,
   capture output and Web UI access on port 8631. No physical print is expected.

Local validation: 23 unit tests, repository isolation checks, shell syntax,
Python compilation and diff whitespace checks pass. Docker/Podman, ARM64 image
build and HAOS/hardware validation are unavailable in this worker; no successful
physical discovery or printing is claimed.


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
