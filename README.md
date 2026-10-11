# HP Color Laser 150a: CUPS 3 retrofit PoC, phase 1

**Experimental PoC, not a working printer release.** The separate working
[CUPS 2.4 release](https://github.com/Deluka-BE/haos-cups-hp150) is untouched.
Version 0.1.12 enables manually selected USB hardware-test printing alongside
capture diagnostics. Keep the working app and its configuration untouched.

## Install on Home Assistant OS (2026.10)

1. On an **aarch64/ARM64** HAOS system, open **Settings → Apps → App store**
   (called **Add-ons → Add-on store** in older interfaces).
2. Open the top-right **⋮ → Repositories**, enter
   `https://github.com/Deluka-BE/haos-cups3-hp150-poc`, and click **Add**.
   Close the dialog; refresh the store if needed. If the previous attempt is
   cached, remove this PoC URL and add it again.
3. Select **HP 150 CUPS 3 Retrofit PoC (USB test)** and click **Install**.
   Supervisor builds the Debian image locally; compiling upstream sources can
   take several minutes. This is currently offered only on aarch64.
4. The image build downloads HP's [official ULD archive](https://ftp.hp.com/pub/softlib/software13/printers/MFP170/uld-hp_V1.00.39.12_00.15.tar.gz)
   and verifies SHA256 `cebb9b7b6125e7406634bb9c2a98b01477d1e11d66c7c90474669de9927bc91d`
   before extracting the four required files. No manual driver upload is needed.
   Only the AArch64 filter and library, HP 15x PPD, CMS file and English EULA
   are installed; HP's installer is never executed. The existing validator must
   pass during the build and again at startup. The EULA is available in the
   image at `/usr/share/doc/hp150-uld/eula.txt`; review HP's license before use
   or redistribution. Proprietary files are never committed to Git.
5. In **Configuration → Network**, leave `8631/tcp` mapped to `8631` (or choose
   another unused host port if needed). Keep **Protection mode** enabled.
6. Click **Start**, then inspect **Logs** for driver validation and service startup.
   Click **Open Web UI**, or visit `http://<HAOS-IP>:8631/` using the configured
   host port. This is PAPPL's direct HTTP interface, without ingress or TLS.
   Unlike the loopback-only development command below, HAOS publishes this port
   to the host network interfaces; use it on a trusted local network.
7. Follow the 0.1.12 capture and separate USB queue test steps below. This is not
   an installation of CUPS 3. Physical printing requires manual submission. Automatic
   boot is disabled. The optional watchdog checks TCP reachability only, not
   driver correctness or conversion success; enable it only after successful startup.

The app retains the existing `/work` layout. Captures, spool and state there are
experimental container-local data, not persistent `/data` storage or backed-up
app configuration; export evidence before updates, rebuilds or uninstalling.
The driver files are baked into `/hp-driver`. Version 0.1.12 requests raw USB
mapping for discovery and manual test printing; no driver-directory mount or user option is needed.

The previous standalone Docker layout lacked root `repository.yaml` and an app
subdirectory with `config.yaml`. Home Assistant therefore could not recognize
it as an installable app repository. The Dockerfile, scripts and tests now live
in `cups3_hp150_poc/`, which is the complete image build context.
See [repository requirements](https://developers.home-assistant.io/docs/apps/repository/)
and [current app metadata](https://developers.home-assistant.io/docs/apps/configuration/).
No legacy `build.yaml` or implicit `BUILD_FROM` is used.

This separate repository explores the least disruptive migration path: an IPP
Printer Application around the established HP ULD PPD/filter stack. It does not
install CUPS 3 or a CUPS scheduler. A future CUPS 3 client should see the PAPPL
application as a driverless IPP printer.

```text
IPP client -> PAPPL / Legacy Printer Application -> libppd / libcupsfilters2
           -> HP rastertospl + libscmssc.so + cms/15xsc.cts -> capture file OR CUPS USB backend -> HP USB printer
```

The working `Deluka-BE/haos-cups-hp150` CUPS 2.4 release is outside this PoC's
scope. Do not mount, modify, or use its state/spool directories. No HP files are
included in Git or the image build context. Review HP's license before redistributing images containing the staged files.

## Build choices and prerequisites

Use a native Debian-compatible ARM64 Docker host (or buildx/QEMU for building).
HP executables must actually be AArch64; an ARM64 container cannot run an x86
ULD filter. Host prerequisites: Docker/buildx, Python 3, `file`, `readelf`
(binutils), and curl. HAOS itself is not assumed to provide Docker CLI access;
use a separate development host for this first phase.

Debian trixie supplies `libpappl-dev` (1.3.1 series) and `libcupsfilters2-dev`
(2.0.0 series). OpenPrinting libppd 2.0.0 is built from pinned commit
`62666f01b167bdf5975b08fbab5c2f34d9277db3`: trixie lacks its development
package, and the older distribution package called `libppd-dev` is unrelated. The older similarly named
`libcupsfilters-dev` is **not** the required version 2 library. Debian packages
track trixie security updates rather than exact versions; the image records the
resolved package manifest at `/usr/share/hp150-package-versions.txt`. The base
image tag is mutable; record its digest for any repeatable experiment.

pappl-retrofit is built from commit
`49ad525a3715a57aae24c715ef0767b55ffb1991`, fetched and checked by SHA, not a
floating branch. This revision includes fixes after the 1.0b2 release. Review
API/build compatibility when deliberately updating it. Build tools remain in the
phase 1 image for diagnosis. No CUPS service, Avahi daemon, or USB device is
started. Built-in PAPPL backends are disabled by upstream default; the Dockerfile
also changes the Legacy application allowlist to `capture,usb` and disables device
PostScript default queries. Only our dedicated backend directory is used.

References: [upstream architecture and paths](https://github.com/OpenPrinting/pappl-retrofit),
[pinned source](https://github.com/OpenPrinting/pappl-retrofit/tree/49ad525a3715a57aae24c715ef0767b55ffb1991),
[Debian PAPPL](https://packages.debian.org/trixie/libpappl-dev),
[Debian filter v2 development package](https://packages.debian.org/trixie/libcupsfilters2-dev),
[pinned libppd](https://github.com/OpenPrinting/libppd/tree/62666f01b167bdf5975b08fbab5c2f34d9277db3).

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

## USB permission fix (0.1.11; historical)

HAOS 0.1.10 confirms a Unix permission failure: HP `03f0:ea2a` is visible,
its usbfs node is `uid=0 gid=7 mode=0664`, while UID 10001 cannot read, write
or open it (`EACCES`). CUPS reports libusb open error `-3` and no HP URI;
interface 00 is class 07/subclass 01/protocol 02 with `usblp` attached.

This release adds Home Assistant's supported
[`usb: true` mapping](https://developers.home-assistant.io/docs/apps/configuration/)
for `/dev/bus/usb` and its USB device policy. Mapping alone does not override
Unix permissions. A small Python bootstrap starts as container root, removes
both token aliases immediately, reads only bounded numeric identity/location
fields from USB sysfs, and selects the group of the matching HP usbfs character
node (major 189). It replaces supplementary groups with those HP node GIDs,
sets all real/effective/saved GIDs and UIDs to 10001, enables Linux
`no_new_privs`, then execs the existing entrypoint. Identity setup failure
refuses launch; an absent printer still allows the capture service to start.
GID 7 is not hardcoded, no group database is changed, root-group membership is
never granted, and no host node is chmodded/chowned. Existing runtime checks,
HP filter chain, token unsetting, capture verifier and port 8631 are retained.

An unprivileged process cannot dynamically add a supplementary GID. This
release therefore needs a brief root bootstrap with Docker's default SETUID
and SETGID capabilities; the application, discovery probes, filters and backends
run as UID 10001 with no new privileges. It requests no additional capabilities,
`privileged` list, `full_access`, host directory mounts or Supervisor API access.
Keep HAOS Protection mode and AppArmor enabled. The USB mapping exposes raw USB
nodes; group membership also allows access to other mapped nodes sharing the
HP GID. This is a group-based permission fix, not per-device isolation. The
application still accepts only capture output and never submits a USB print
job. CUPS discovery can claim interfaces/detach `usblp` as documented below.

Connect/power on the HP before startup. If plugged in later, or its group changes,
restart the PoC so the GID is derived again. A root-owned group, missing sysfs
identity, changed mode, AppArmor denial or device-policy denial can still block
access; do not disable protection or broaden permissions to mask that result.

Exact next HAOS validation:

1. Export any PoC captures first. Refresh this repository in the store, update
   to **0.1.11** and let Supervisor rebuild the image and recreate the container.
   A restart of the 0.1.10 image is insufficient. Reinstall is only needed if
   the store does not offer the update/rebuild; verify installed version 0.1.11.
   Keep 8631 mapped and Protection mode enabled. Leave production apps unchanged.
2. With HP connected and idle, start the PoC. Confirm
   `USB runtime: uid=10001 gid=10001 HP supplementary-gids=[7]` for the observed
   node (a different numeric group is valid if the HP node uses it).
3. Confirm `HP-node ... current-uid=10001 readable=True writable=True` and
   `HP-node open-rw=ok (no I/O performed)`. These are the permission acceptance
   criteria; enumeration alone is insufficient.
4. Inspect sanitized `cups-usb evidence` and
   `discovery=cups-usb ... HP-Color-Laser-150a=visible`, ideally followed by a
   matching `usb://HP/Color%20Laser%20150a?...` URI. If still not reported despite
   open success, capture detach/claim/driver-check evidence, interface descriptors
   and discovery status for the next investigation. Do not unbind `usblp` or
   add a physical queue in this release. URI output may contain a serial number;
   redact that when sharing outside the hardware investigation.
5. Confirm `USB printing disabled; PAPPL allowlist=capture`, access the Web UI at
   `http://<HAOS-IP>:8631/`, repeat the proven `cups:capture:/hp150` capture test,
   and confirm automatic QPDL PASS and saved capture. No physical page is expected.

Local checks: 29 unit tests, repository/static checks, Python compilation, shell
syntax and diff whitespace validation pass. No Docker/Podman, ARM64 image build
or HAOS hardware test is available here; read/write success and discovery remain
hardware validation targets, not claimed results.

## Historical USB blocker diagnostics (0.1.10)

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

Local 0.1.6 checks passed: all seven tests, the repository validator, three shell
syntax checks, Python compilation and whitespace checks.
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

## Port restoration and source findings

Version 0.1.4 incorrectly inferred that the 0.1.3 port mapping was broken from
PAPPL log lines showing `:863`. The user confirmed that deployed HAOS 0.1.3
was empirically reachable at `http://192.168.0.3:8631/` and showed the PAPPL/CUPS
page. That observation contradicts the claimed reachability failure.

Version 0.1.5 restores the known-good 0.1.3 configuration: PAPPL is intended
and configured on **8631**, HAOS publishes `8631/tcp: 8631`, and Web UI and
watchdog use `[PORT:8631]`. Container URLs also use `localhost:8631`.
After updating from 0.1.4, check Configuration → Network maps `8631/tcp` to
`8631`; Supervisor may retain user network settings.

Source review does **not** prove the cause of the `:863` log discrepancy:

- Pinned [retrofit `_prSystemCB()`](https://github.com/OpenPrinting/pappl-retrofit/blob/49ad525a3715a57aae24c715ef0767b55ffb1991/pappl-retrofit/pappl-retrofit.c#L4642)
  reads `server-port` with `cupsGetOption`, converts it with `atoi`, and passes
  the integer to `papplSystemCreate` at lines 4768–4777.
- [PAPPL v1.3.1 option handling](https://github.com/michaelrsweet/pappl/blob/v1.3.1/pappl/mainloop.c#L273)
  passes `-o` to `cupsParseOptions`; the reviewed
  [CUPS 2.4.10 parser](https://github.com/OpenPrinting/cups/blob/v2.4.10/cups/options.c#L260)
  preserves the full numeric value.
- [PAPPL system creation](https://github.com/michaelrsweet/pappl/blob/v1.3.1/pappl/system.c#L185)
  stores the integer unchanged. [Listener creation and logging](https://github.com/michaelrsweet/pappl/blob/v1.3.1/pappl/system-accessors.c#L2478)
  formats the service in a 255-byte buffer, passes the port to `httpAddrListen`,
  and logs the same integer with `%d`.

These reviewed sources preserve 8631; they establish neither truncation nor a
reason to change the working mapping. PAPPL/CUPS are Debian packages rather than
Git-pinned dependencies; the deployed image and package manifest still need
checking. The discrepancy remains diagnostic. No upstream port patch is added.

Immediately before server exec, startup now prints the effective validated
`POC_PORT` and each indexed argument from the same argument list passed to exec.
Only the numeric port and fixed service arguments are logged; no environment,
credentials or document content is dumped. Default/override validation and driver
staging retain their 0.1.3 behavior.

`Unable to initialize DNS-SD: Daemon not running` remains expected: no Avahi daemon
is started. PAPPL logs this separately from TCP listener creation; the supplied
runtime proceeded to listen. Discovery/advertisement is a later issue and is
not required to open the direct HTTP URL. No DNS-SD daemon, USB access, device
mounts or privileged mode are added.

HAOS runtime verification remains required: rebuild/install on ARM64, compare
the launch diagnostics with the full PAPPL listener logs and package manifest,
open host `:8631`, and check Open Web UI and the optional TCP watchdog. Capture
conversion, dynamic linking and CMS lookup still need separate runtime testing.
Local 0.1.5 validation passed: repository/isolation checks, all six synthetic tests,
three shell syntax checks, Python compilation and whitespace checks. A shell
harness with driver preparation stubbed verified default/empty/explicit 8631,
numeric overrides, malformed/too-large port rejection, modes, and exact
diagnostic/exec arguments. The original shell range expression also permits
below-1024 overrides because its first test is in an AND list; that pre-existing
behavior is preserved here, and HAOS uses the default 8631.
Docker/Podman, ShellCheck and Hadolint are unavailable in this worker.
Local checks cannot establish runtime acceptance or a usable printer release.

## Build-time HP staging

`scripts/stage-hp-uld.sh` downloads and checks the pinned official archive during
image build. It rejects any `BUILD_ARCH` other than `aarch64` and any Debian
image architecture other than `arm64`. It extracts only these payload files:

```text
/hp-driver/HP_Color_Laser_15x_Series.ppd
/hp-driver/rastertospl
/hp-driver/libscmssc.so
/hp-driver/cms/15xsc.cts
/usr/share/doc/hp150-uld/eula.txt
```

The filter has mode 755; data, library and EULA have mode 644. The temporary
archive and extraction directory are removed in the same build step. Download,
hash, extraction or validation failure stops the build. No HP USB helper,
backend, scanner or installer is installed.

The validator reports component hashes, PPD declarations, ELF architecture and
dynamic dependencies using `readelf`; it never executes the HP filter or `ldd`.
Startup copies the validated files to `/work`, including the relative
`/work/filter/cms/15xsc.cts` path, and sets `LD_LIBRARY_PATH=/work/lib`.
Dynamic linking and actual CMS lookup still need ARM64 runtime testing.

## Build and isolated capture smoke test

```sh
docker buildx build --platform linux/arm64 --load -t hp150-poc:phase1 cups3_hp150_poc
mkdir -p run-data/state run-data/spool run-data/capture
# Container runs as UID/GID 10001; grant it access to this PoC directory only.
sudo chown -R 10001:10001 run-data
# Validate/inspect and enumerate PPDs before starting a service.
docker run --rm --platform linux/arm64 \
  -v "$PWD/run-data:/work" \
  hp150-poc:phase1 validate
docker run --rm --platform linux/arm64 \
  -v "$PWD/run-data:/work" \
  hp150-poc:phase1 drivers
export POC_PORT=8631
docker run -d --name hp150-poc --platform linux/arm64 \
  --cap-drop=ALL --cap-add=SETUID --cap-add=SETGID \
  --security-opt=no-new-privileges \
  -p "127.0.0.1:$POC_PORT:8631" \
  -v "$PWD/run-data:/work" \
  hp150-poc:phase1
POC_PORT="$POC_PORT" cups3_hp150_poc/scripts/smoke.sh
docker logs --tail 200 hp150-poc
docker exec hp150-poc cat /usr/share/hp150-package-versions.txt
```

`POC_PORT` in this host-side example selects the external port (default 8631).
The container defaults to 8631, matching `EXPOSE 8631`; the example does not pass
an environment override. The entrypoint retains 0.1.3 override handling; changing the internal port requires matching publication.
Docker publishes only host loopback in this example. State, spool, copied
PPDs, filter and libraries are confined to `run-data/`. Use fresh directories per
experiment. No `--privileged`, `--device`, `/dev/bus/usb`, host networking, CUPS
socket or existing printer state mounts. The smoke script checks HTTP and the
HP driver listing; **it does not prove filter execution or SPL output**.
Inspect the driver listing and debug logs if enumeration fails.

## End-to-end capture test (0.1.8)

Rebuild/update this PoC to **0.1.8**, then open `http://<HAOS-IP>:8631/`.
Use PAPPL's **Add Printer** page, select **HP150 file capture** (device URI
`cups:capture:/hp150`), and explicitly select **HP Color Laser 15x Series**
from the driver list. Name it `hp150-capture`. Check the printer page shows
that driver and capture URI before submitting. The discovery record includes
HP's matching IEEE-1284 identity; manual driver selection avoids ambiguity.
Existing capture queues can be reused after checking their driver and URI.

On that printer's page, use the normal **Print Test Page** action. The pinned
Legacy application installs `testpage.pdf` and its test-page callback submits
it through the regular PAPPL job/conversion path. Alternatively submit a small
known one-page PDF to the exact IPP printer URI displayed by PAPPL from a normal
IPP client; do not guess the URI. No custom HTTP endpoint or direct filter
submission is needed. Wait for the job to complete and record its job id.

The log must show `Using CUPS filter (printer driver): /work/filter/rastertospl`,
the wrapper's `HP150 invoking /work/filter/rastertospl.real` diagnostic,
ULD's CMS initialization/lookup messages without errors, and an automatic `PASS: capture job=… bytes=… sha256=…
format=QPDL-declared signature=PJL-QPDL` line. Each nonempty invocation writes
`/work/capture/job-<id>-<unique>.spl` plus `.spl.json`; retries cannot overwrite
previous captures. JSON contains only UTC timestamp, numeric job id, byte count,
hash and basename, never user, title, options or environment. Administrative
opens with no data produce no files. Metadata records received bytes, not a
conversion-success claim: failed filters can leave partial nonempty output.
Job completion, filter logs and output verification must all agree.

From a development host with Docker access to the experimental container,
optionally recheck the exact capture matched by job id in `/work/capture` (HAOS itself need not have Docker CLI):

```sh
docker exec hp150-poc python3 /opt/poc/scripts/verify-capture.py \
  /work/capture/job-1-REPLACE_WITH_ACTUAL_SUFFIX.spl
# Export the bytes and metadata before updating/removing the app.
docker cp hp150-poc:/work/capture ./capture-evidence
```

On HAOS, verification runs automatically after both capture files are finalized;
the single PASS/FAIL line contains only job id, size, hash and fixed format/signature labels.
A failed check returns backend failure and retains the completed bytes/metadata
for diagnosis. Empty administrative opens remain silent and create no capture.
The log omits paths, user, title, options, environment and document bytes; a host administrator
with access to the PoC container can run the same verifier and export captures.
There is no added capture-download web endpoint. The verifier checks metadata
against bytes, including matching numeric job id and filename, and a complete
`@PJL ENTER LANGUAGE = QPDL` line in a stream-start PJL header.
`QPDL-declared` means a language declaration was detected, not validated QPDL
page data. The verifier does not parse QPDL records or establish stream completeness. It rejects ordinary PDF/raster renamed `.spl`. Framing
alone does not prove complete page data, CMS use, or physical printer acceptance.
Keep captured document contents local.

### Filter/backend architecture and lookup

Pinned retrofit `print-job.c` appends the PPD external filter and then
`_prPrintFilterFunction` to the chain. Its CUPS device path launches our backend
with the job's filter data and writes the final stream to backend stdin.
Thus capture already sits after `rastertospl`; no architectural replacement
is necessary. The backend answers CUPS fd 4 GET_STATE/GET_CONNECTED for the
virtual writable sink, GET_BIDI as unsupported, and GET_DEVICE_ID with the HP
identity. Other requests return NOT_IMPLEMENTED, including drain/reset;
there is no physical printer or bidirectional printer traffic.

The original relative `/work/filter/cms` layout did not match the ULD lookup.
Inspection of the hash-verified ARM64 binary finds `CUPS_DATADIR` and
`%s/model/uld-%s/cms/%s`; its manufacturer conversion lowercases `HP`, the
PPD's `linuxIdentify` is `15x`, and libscmssc appends `sc.cts`.
Startup stages `/work/share/cups/model/uld-hp/cms/15xsc.cts`; the HP wrapper
exports `CUPS_DATADIR=/work/share/cups` only for the vendor filter, preserving
the standard data lookup for other conversion filters. The executable wrapper keeps the PPD's normal
`rastertospl` name, fixes library/CMS variables before exec, and invokes the
unchanged vendor binary at `/work/filter/rastertospl.real`. stdout is untouched.
`LD_LIBRARY_PATH=/work/lib` supplies `libscmssc.so`; startup now checks actual
library loading (including CUPS ABI libraries), executable/readable components,
and writable capture/spool/state directories. Neither checker nor wrapper dumps
the environment, job arguments, or loader error text. HAOS token sanitization
remains in place for the application and children.

Local checks cover binary-preserving capture, retry uniqueness, metadata hashes,
empty administrative opens, failed input cleanup/redaction, fragmented side-channel
requests, runtime paths/permissions, and token removal. They do **not** execute
ARM64 ULD or PAPPL here: Docker/Podman, ARM64 runtime and HAOS are unavailable.
The ARM64 image build, UI queue creation, test-page conversion, actual CMS lookup,
job completion and automatic capture-verifier integration remain HAOS acceptance steps.
The user has since confirmed the 0.1.7 HAOS ARM64 capture path; 0.1.8 preserves
that software path and requires a runtime check of the new automatic PASS/FAIL reporting.

## Phased acceptance and cleanup

1. **Local scaffold:** static shell/Python checks and synthetic capture tests.
2. **ARM64 container:** successful build, package manifest, validation with real
   ULD files, HTTP response and PPD enumeration. No print job yet.
3. **Capture conversion:** one-page IPP job, filter trace and validated SPL file;
   investigate dependency/CMS/side-channel issues within the isolated container.
4. **Future hardware phase:** separately authorized USB experiment after capture
   acceptance. No automatic USB support or production rollout in this phase.

```sh
python3 validate_repository.py  # Requires PyYAML on the development host.
python3 -m unittest discover -s cups3_hp150_poc/tests -v
sh -n cups3_hp150_poc/scripts/entrypoint.sh
sh -n cups3_hp150_poc/scripts/smoke.sh
sh -n cups3_hp150_poc/scripts/stage-hp-uld.sh
docker logs hp150-poc > run-data/container.log
docker stop hp150-poc
docker rm hp150-poc
# Optional: delete only this PoC's generated state/output after saving evidence.
sudo rm -rf "$PWD/run-data"
```

Version 0.1.3 validation: the official archive was downloaded and its pinned
SHA256 matched. The existing validator passed on the four real extracted files,
including both AArch64 ELF checks. A local staging harness (temporary output
paths, cached archive and simulated Debian architecture) checked exact payload,
filter mode 755, EULA retention and both architecture rejection paths. This is
not an image build. Docker/Podman and printer hardware are absent here; ARM64
image build and HAOS runtime were not tested in that worker. The subsequently
supplied HAOS 0.1.3 evidence confirms staging, validation, PPD loading and a
PAPPL log reporting `:863`, while the user confirmed the page was reachable
on host `:8631`. The log discrepancy remains unexplained; dynamic linking during
conversion and IPP conversion were not demonstrated. Test startup with the printer physically unplugged.

Repository conversion validation: `validate_repository.py` checks YAML syntax,
required metadata, a single app, build inputs, capture/USB access settings, and Git/
Docker exclusions for HP files. All six synthetic PoC tests, all shell syntax
checks and `git diff --check` passed locally. Metadata was compared with the
current Home Assistant documentation and Supervisor schema; the full Supervisor
validator and official container builder/linter were not run. The user has confirmed the deployed 0.1.3 web page on host `:8631`; the next
version image build, Web UI shortcut and watchdog still require runtime checks.
