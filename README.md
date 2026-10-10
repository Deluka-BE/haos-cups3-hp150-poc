# HP Color Laser 150a: CUPS 3 retrofit PoC, phase 1

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
included in Git or the image build context. Do not publish images with locally
staged proprietary files without checking the relevant license.

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

## Stage locally

Obtain the HP ULD components from your own legally obtained driver distribution.
Select the ARM64 binaries, not similarly named x86/ARM32 files. Stage exactly:

```text
hp-driver/
  HP_Color_Laser_15x_Series.ppd
  rastertospl
  libscmssc.so
  cms/15xsc.cts
```

The entire `hp-driver/` path is gitignored and dockerignored. Files must be
nonempty regular files; symlinked components are rejected. Run:

```sh
python3 scripts/validate-driver.py hp-driver
```

Validation reports all missing files, SHA-256 hashes, PPD filter declarations,
ELF machine types and NEEDED/RPATH/RUNPATH entries. It uses `readelf`, never
executes a filter or invokes `ldd`. Hashes are experiment identifiers, not
vendor authenticity checks. Dynamic dependency resolution and ABI compatibility
still require testing inside Debian. Startup copies the files into `/work` and
makes the filter executable, so no host executable permission is required.

## Build and isolated non-USB smoke test

```sh
docker buildx build --platform linux/arm64 --load -t hp150-poc:phase1 .
mkdir -p run-data/state run-data/spool run-data/capture
# Container runs as UID/GID 10001; grant it access to this PoC directory only.
sudo chown -R 10001:10001 run-data
# Validate/inspect and enumerate PPDs before starting a service.
docker run --rm --platform linux/arm64 \
  -v "$PWD/hp-driver:/hp-driver:ro" -v "$PWD/run-data:/work" \
  hp150-poc:phase1 validate
docker run --rm --platform linux/arm64 \
  -v "$PWD/hp-driver:/hp-driver:ro" -v "$PWD/run-data:/work" \
  hp150-poc:phase1 drivers
export POC_PORT=8631
docker run -d --name hp150-poc --platform linux/arm64 \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -p "127.0.0.1:$POC_PORT:$POC_PORT" -e POC_PORT \
  -v "$PWD/hp-driver:/hp-driver:ro" -v "$PWD/run-data:/work" \
  hp150-poc:phase1
POC_PORT="$POC_PORT" scripts/smoke.sh
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
python3 -m unittest discover -s tests -v
sh -n scripts/entrypoint.sh
sh -n scripts/smoke.sh
docker logs hp150-poc > run-data/container.log
docker stop hp150-poc
docker rm hp150-poc
# Optional: delete only this PoC's generated state/output after saving evidence.
sudo rm -rf "$PWD/run-data"
```

Worker validation: synthetic backend and missing/invalid driver checks are
available here. Docker/Podman, staged HP files and printer hardware are absent;
image build, service startup, ARM64 filter linking, IPP conversion and hardware
printing must be run on the development host. See the implementation report for
what was actually executed.
