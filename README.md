# HP Color Laser 150a: CUPS 3 retrofit PoC, phase 1

**Experimental PoC, not a working printer release.** The separate working
[CUPS 2.4 release](https://github.com/Deluka-BE/haos-cups-hp150) is untouched.
This app cannot access USB and only writes capture files. Do not change the
connected printer or the working app to try this PoC.

## Install on Home Assistant OS (2026.10)

1. On an **aarch64/ARM64** HAOS system, open **Settings → Apps → App store**
   (called **Add-ons → Add-on store** in older interfaces).
2. Open the top-right **⋮ → Repositories**, enter
   `https://github.com/Deluka-BE/haos-cups3-hp150-poc`, and click **Add**.
   Close the dialog; refresh the store if needed. If the previous attempt is
   cached, remove this PoC URL and add it again.
3. Select **HP 150 CUPS 3 Retrofit PoC (non-USB)** and click **Install**.
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
7. Use only the `cups:capture:/hp150` queue described below. This is not an
   installation of CUPS 3 and does not print to the attached printer. Automatic
   boot is disabled. The optional watchdog checks TCP reachability only, not
   driver correctness or conversion success; enable it only after successful startup.

The app retains the existing `/work` layout. Captures, spool and state there are
experimental container-local data, not persistent `/data` storage or backed-up
app configuration; export evidence before updates, rebuilds or uninstalling.
The driver files are baked into `/hp-driver`; no app configuration or device
mount is needed.

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
           -> HP rastertospl + libscmssc.so + cms/15xsc.cts -> capture file
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
also changes the Legacy application allowlist to `capture` and disables device
PostScript default queries. Only our dedicated backend directory is used.

References: [upstream architecture and paths](https://github.com/OpenPrinting/pappl-retrofit),
[pinned source](https://github.com/OpenPrinting/pappl-retrofit/tree/49ad525a3715a57aae24c715ef0767b55ffb1991),
[Debian PAPPL](https://packages.debian.org/trixie/libpappl-dev),
[Debian filter v2 development package](https://packages.debian.org/trixie/libcupsfilters2-dev),
[pinned libppd](https://github.com/OpenPrinting/libppd/tree/62666f01b167bdf5975b08fbab5c2f34d9277db3).

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

## Build and isolated non-USB smoke test

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
  --cap-drop=ALL --security-opt=no-new-privileges \
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

## End-to-end capture test (0.1.7)

Rebuild/update this PoC to **0.1.7**, then open `http://<HAOS-IP>:8631/`.
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
ULD's CMS initialization/lookup messages without errors, and a `Captured job=…`
line with nonzero bytes and SHA-256. Each nonempty invocation writes
`/work/capture/job-<id>-<unique>.spl` plus `.spl.json`; retries cannot overwrite
previous captures. JSON contains only UTC timestamp, numeric job id, byte count,
hash and basename, never user, title, options or environment. Administrative
opens with no data produce no files. Metadata records received bytes, not a
conversion-success claim: failed filters can leave partial nonempty output.
Job completion, filter logs and output verification must all agree.

From a development host with Docker access to the experimental container,
verify the exact capture named in its log (HAOS itself need not have Docker CLI):

```sh
docker exec hp150-poc python3 /opt/poc/scripts/verify-capture.py \
  /work/capture/job-1-REPLACE_WITH_ACTUAL_SUFFIX.spl
# Export the bytes and metadata before updating/removing the app.
docker cp hp150-poc:/work/capture ./capture-evidence
```

On HAOS, the capture log already exposes size/hash/path; a host administrator
with access to the PoC container can run the same verifier and export captures.
There is no added capture-download web endpoint. The verifier checks metadata
against bytes and the pinned filter's `@PJL ENTER LANGUAGE = QPDL` framing;
SPL-C uses QPDL here. It rejects ordinary PDF/raster renamed `.spl`. Framing
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
job completion and captured QPDL verification remain HAOS acceptance steps.

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
required metadata, a single app, build inputs, non-USB access settings, and Git/
Docker exclusions for HP files. All six synthetic PoC tests, all shell syntax
checks and `git diff --check` passed locally. Metadata was compared with the
current Home Assistant documentation and Supervisor schema; the full Supervisor
validator and official container builder/linter were not run. The user has confirmed the deployed 0.1.3 web page on host `:8631`; the next
version image build, Web UI shortcut and watchdog still require runtime checks.
