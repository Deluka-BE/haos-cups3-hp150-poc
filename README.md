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
  -p "127.0.0.1:$POC_PORT:$POC_PORT" -e POC_PORT \
  -v "$PWD/run-data:/work" \
  hp150-poc:phase1
POC_PORT="$POC_PORT" cups3_hp150_poc/scripts/smoke.sh
docker logs --tail 200 hp150-poc
docker exec hp150-poc cat /usr/share/hp150-package-versions.txt
```

Port must be 1024–65535; default is 8631. The application listens inside the
container, but Docker publishes only host loopback. State, spool, copied PPDs,
filter and libraries are confined to `run-data/`. Use fresh directories per
experiment. No `--privileged`, `--device`, `/dev/bus/usb`, host networking, CUPS
socket or existing printer state mounts. The smoke script checks HTTP and the
HP driver listing; **it does not prove filter execution or SPL output**.
Inspect the driver listing and debug logs if enumeration fails.

## Capture scaffold and exact remaining runtime test

The `capture` backend implements CUPS discovery and stdin/filename input. It
accepts only `capture:/hp150`, writes unique `job-*.spl` files via temporary files
and atomic rename, and never opens a device. pappl-retrofit wraps CUPS backend
URIs with `cups:`, so the application queue URI is `cups:capture:/hp150`.

After the smoke test, open `http://127.0.0.1:8631/` and add a queue using the
capture device and the staged HP driver. Alternatively, after confirming the
runtime driver identifier and CLI help:

```sh
docker exec hp150-poc legacy-printer-app --help
# Replace DRIVER_ID with the exact identifier from the drivers listing.
docker exec hp150-poc legacy-printer-app add -u ipp://localhost:8631/ \
  -d hp150-capture -v cups:capture:/hp150 -m DRIVER_ID
# Inspect the actual queue URI in the UI/printer listing before submitting.
docker exec hp150-poc legacy-printer-app printers -u ipp://localhost:8631/
```

For the later runtime test, copy a small known one-page PDF to `/work/sample.pdf`
and submit it to that **capture queue only**, using its actual displayed IPP URI
and `ipptool` Print-Job or `legacy-printer-app submit`. Record the completed job
status, debug filter invocation, byte count, SHA-256, and a hex inspection of
`run-data/capture/job-*.spl`. A filename ending in `.spl` alone proves nothing:
confirm `rastertospl` executed and produced plausible SPL data, not PDF/raster.
Keep output local; it may contain document content.

This backend is a safe scaffold: PAPPL/retrofit discovery, URI handling, job
completion and side-channel behavior have not been tested in this worker.
It does not implement bidirectional CUPS side-channel responses. If the runtime
waits on such queries, diagnose the logs and add explicit unsupported responses
before claiming completion. Confirm ULD CMS lookup: startup provides
`/work/filter/cms/15xsc.cts`, runs in `/work/filter`, and sets
`LD_LIBRARY_PATH=/work/lib`. The binary may require another hard-coded CMS path
or extra libraries. Do not guess success or work around it by connecting USB.

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
image build, HAOS startup, port 8631, dynamic linking and IPP conversion remain
unverified. Test startup with the printer physically unplugged.

Repository conversion validation: `validate_repository.py` checks YAML syntax,
required metadata, a single app, build inputs, non-USB access settings, and Git/
Docker exclusions for HP files. All six synthetic PoC tests, all shell syntax
checks and `git diff --check` passed locally. Metadata was compared with the
current Home Assistant documentation and Supervisor schema; the full Supervisor
validator and official container builder/linter were not run. No HAOS repository
addition, installation, image build, web UI or watchdog runtime success is claimed.
