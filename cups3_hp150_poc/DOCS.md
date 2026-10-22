# Release 0.1.28: minimal HP vendor quality experiment

The supplied 0.1.27 boundary findings show the bad CUPS 3 invocation using `Screen=PrinterDefault` and `secSaturation=70`, differing from the HP PPD/default/good-reference behavior. This release tests that difference at the vendor filter boundary. The archived pinned HP 15x PPD was checked locally; its explicit defaults are:

| Option | Normalized value |
| --- | --- |
| Screen | Enhanced |
| secBrightness | 50 |
| secContrast | 50 |
| secSaturation | 50 |
| CyanRed | 50 |
| MagentaGreen | 50 |
| YellowBlue | 50 |

`job-stage.py` rewrites only argv[5] immediately before supervising rastertospl. Each key is normalized only if the active PPD explicitly declares the expected default above. All occurrences of that key (including case variants) are removed and one canonical value is appended, including when the key was absent. Unrelated option tokens retain their quoting, escapes, values and order; separating whitespace is canonicalized. Malformed quoted options or an unreadable PPD reject the filter invocation with a fixed diagnostic rather than launching with ambiguous options. This experiment deliberately overrides explicit user choices for these seven controls.

PDF-to-raster generation, Quality/resolution, media geometry, USB transport, CMS/vendor binaries and CUPS 2.4 are unchanged. The disabled-by-default diagnostic capture is preserved: its boundary JSON records the actual **normalized** argv passed to the vendor, with the same private permissions, allowlisted environment, PPD/resource hashes and stream capture. Retain the original 0.1.27 evidence separately for comparison.

Build/install local 0.1.28 on the ARM64 HA host using the existing procedure. Use the same queue, source document and print settings as 0.1.27 and the good reference; enable `capture_raster_once`, restart, and submit one job. Follow the four-file copy and hash verification procedure in the historical 0.1.27 section below, substituting version 0.1.28. Verify the normalized boundary options and unchanged input raster hash where deterministic, then compare the physical pages. Disable capture and restart after collecting evidence. Do not change CUPS 2.4.

Worker validation: repository validation passed; all six focused quality tests and nine existing raster-capture tests passed. Full unittest discovery ran 121 tests: 113 passed, eight skipped, plus one class setup error because the existing PDF metadata tests require an unavailable C compiler. Python compilation, shell syntax checks and `git diff --check` passed. No ARM64 image build or physical print was performed.

Remaining uncertainty: the original captured bundles are not present in this worker; the boundary finding above comes from the supplied report. Vendor behavior, output structure and physical print quality require ARM64/HP hardware validation. This is an experiment, not a verified quality repair; changed SPL size/hash alone does not establish improved quality.

# Release 0.1.27: rastertospl boundary evidence; quality fix pending

This worker has no CUPS 2.4/3 reference raster/SPL captures or CUPS 2.4 invocation evidence. No causal A/B or physical print validation is possible with the supplied files. The archived ULD package is present, but the runtime is ARM64 and the worker is x86_64 without Docker. A size difference alone cannot identify a halftoning cause. No vendor option, library lookup or CUPS 2.4 installation is changed.

Source findings: the archived HP 15x PPD defaults to `ColorModel=RGB`, `Quality=600x600_2` (Best), `Screen=Enhanced`, `Trapping=Medium`, `TonerSaveMode=Standard`, `secBrightness=50`, `secContrast=50`, `secSaturation=50`, `YellowBlue=50`. `Quality=600x600_1` (Normal) also requests 600x600 dpi. Consequently matching raster dimensions/color depth do not establish equivalent vendor quality. The pinned retrofit `_prCreateJobData` in `pappl-retrofit/print-job.c` adds libppd color/quality presets, content-optimization presets, then vendor options selected from job attributes or printer defaults. This is a plausible source of a changed option, not a proven root cause. HP resource lookup already sets `LD_LIBRARY_PATH=/work/lib` and `CUPS_DATADIR=/work/share/cups`; the staged CTS path is `/work/share/cups/model/uld-hp/cms/15xsc.cts`.

With `capture_raster_once: true`, 0.1.27 additionally writes `cups3-reference.boundary.json` (0600) beside the existing streams. It contains the actual child argv including argv[0], exact mapped CUPS option string at argv[5], allowlisted child environment including the diagnostic LD_PRELOAD, full active PPD text/path/hash and vendor binary/library/CMS file identities. The existing `.meta.txt` includes `boundary_sha256`; require a matching hash and `capture status=complete` for the current job. Boundary write failure reports `boundary status=unavailable` and printing continues. The allowlist excludes service tokens and unrelated environment variables. This is not a full environment dump, an IPP request capture, a resolved PPD-mark dump or evidence that the vendor actually opened a CMS file. Original IPP attributes and printer defaults must be exported separately to distinguish upstream mapping from explicit requests. The raw argv contains username/title and possibly filenames: treat the JSON like the sensitive raster data. No such values are logged by the capture code.

Home Assistant test procedure:

1. Build/install local add-on 0.1.27 on the ARM64 HA host using the existing local build procedure; no worker push or release. Keep the same printer queue and source document. Set `capture_raster_once: true` in add-on configuration and restart.
2. Submit exactly one reference job with the same application, media, color, quality and scaling as the good CUPS 2.4 job. Wait for `boundary status=complete` and `capture status=complete` with the same job id. This performs a physical print if the selected queue uses USB; the capture queue writes only to a file.
3. In the HA host shell, set `POC_ADDON_SLUG` to the installed add-on identifier and copy all four files, including JSON:

   ```sh
   mkdir -p ./cups3-reference
   for name in cups3-reference.in.raster cups3-reference.out.spl cups3-reference.meta.txt cups3-reference.boundary.json; do
     docker cp "addon_${POC_ADDON_SLUG}:/share/cups3-capture/$name" "./cups3-reference/$name"
   done
   sha256sum ./cups3-reference/cups3-reference.boundary.json
   ```

4. Compare that SHA-256 with `boundary_sha256` in the copied metadata. Disable `capture_raster_once` and restart after copying. Retain the physical page for comparison.
5. Supply the existing good CUPS 2.4 capture plus its exact filter argv, relevant environment, active PPD and vendor resource hashes, and the CUPS 3 bundle. Do not change CUPS 2.4. Obtain original job IPP attributes and printer defaults from existing exports/logs if available; do not infer them from raster headers. `compare-boundary.py cups24.json cups3.json` diffs matching boundary JSON schemas (exit 1 means differences, 0 identical). It prints private metadata; use a private destination.
6. On an isolated ARM64 runtime, replay the *same* CUPS 3 raster using its captured argv/env/PPD to establish a repeatable baseline. Redirect stdout to a new SPL file and stdin from the captured raster; never invoke a USB backend. If argv[6] supplies a filename, preserve file-input semantics using the captured raster. Then use the CUPS 2.4-equivalent boundary and change one differing option at a time. Prioritize Quality, Screen, TonerSaveMode, remaining color controls, PPD content and CMS lookup. Preserve argv[0] using an exec API with a separate executable argument. Record input SHA-256, exact configuration, exit status, output size/hash and QPDL verification for every trial. Run each configuration twice. Matching output size alone is insufficient; inspect structure and finally compare physical pages before selecting a minimal fix.

Worker validation: the nine capture tests pass, including exact option/PPD preservation, private permissions, credential exclusion and boundary-write failure with continued printing. Repository validation, Python syntax checks and `git diff --check` pass. Full unittest discovery runs 115 tests with zero assertion failures, eight skips and one setup error: the existing PDF metadata class requires an unavailable C compiler. ARM64 image build and physical prints were not run.

The quality correction and its physical acceptance test remain pending the missing evidence. The version bump identifies the new diagnostics, not a verified quality repair.

# Release 0.1.26: one-shot rastertospl IN/OUT capture

This is a temporary diagnostics-only release for direct comparison with the known-good CUPS 2.4 reference. The add-on option `capture_raster_once` defaults to `false`. With it disabled, `job-stage.py` retains the 0.1.25 inherited stdin/stdout execution path: no capture pipe, file, buffering or storage check is introduced.

When `capture_raster_once: true`, the privileged bootstrap validates the option before the permanent UID/GID 10001 drop, prepares only `/run/hp150-raster-capture` and `/share/cups3-capture`, then creates a one-shot `armed` marker. The first rastertospl invocation atomically renames `armed` to `claimed`; later jobs cannot capture again until a restart with the option still enabled. Fixed output names are:

- `cups3-reference.in.raster` — bytes successfully presented to the HP rastertospl child;
- `cups3-reference.out.spl` — bytes emitted by the HP child before backend handoff;
- `cups3-reference.meta.txt` — numeric job id, filter exit status, byte counts, SHA-256 values, CUPS raster magic, output signature/declared format, and the first decoded raster header (width, height, DPI, bit depth, color space/order and row layout). Missing header evidence is explicitly `unavailable`; QPDL detection is declaration evidence, not page validation.

The armed path gives the HP child stdin/stdout pipes and uses two concurrent tee threads while the existing supervisor continues draining sanitized stderr. This avoids the classic stdin/stdout pipe deadlock and leaves fd 3/4 and other inherited CUPS descriptors available because `close_fds=False` remains unchanged. The 0.1.25 `LD_PRELOAD` header shim is still scoped only to rastertospl. Vendor stderr filtering, process-group cancellation, the 180-second deadline and exit-status handling are unchanged. The live OUT stream is forwarded to the backend while it is captured; capture data is never interpreted as image content by the diagnostic code.

Safety bounds are 512 MiB maximum per captured direction. Before starting an armed capture the filesystem must report at least 1152 MiB free, leaving 128 MiB beyond the 1 GiB combined file caps. If preflight fails, printing proceeds without capture. If a capture write or size bound fails mid-job, teeing to the live print path continues and temporary capture files are discarded. Publish errors are reported with a fixed reason. No document bytes, title, username, filename, options, environment, UUID, URI or credentials are logged. Capture directory mode is 0700 and files are 0600. Raw captures are sensitive print data and should be removed after comparison.

Manual HAOS procedure: update to 0.1.26, set `capture_raster_once: true`, restart, then submit exactly one known comparison image with the same queue/settings used for the quality test. Wait for `capture status=complete`, copy the three files from `/share/cups3-capture/`, then set `capture_raster_once: false` and restart. Do not submit a second diagnostic job expecting new files; one-shot state prevents overwrite until re-armed.

Retrieve from the HAOS host shell (replace the slug with the installed add-on's full slug):

```sh
POC_ADDON_SLUG='<repository-prefix>_cups3_hp150_poc'
mkdir -p ./cups3-reference
for name in cups3-reference.in.raster cups3-reference.out.spl cups3-reference.meta.txt; do
  docker cp "addon_${POC_ADDON_SLUG}:/share/cups3-capture/$name" "./cups3-reference/$name"
done
cat ./cups3-reference/cups3-reference.meta.txt
sha256sum ./cups3-reference/cups3-reference.in.raster ./cups3-reference/cups3-reference.out.spl
```

The files also reside in HA's shared directory under `cups3-capture/` (0700 directory, 0600 files, owned by UID 10001); use the host-shell copy above if a share client cannot read them. Metadata is published last: require the current job's `capture status=complete` before copying, because files from an earlier armed run may still exist. Compare the same source image, dimensions, resolution and color settings with `cups24-reference.*`; different raster compression/headers can produce different whole-file hashes even for matching pixels. The raster header records the first page only, as observed by the existing HP decoder shim; stream hashes/byte counts cover the entire job. Disable the option and restart after retrieval, then delete raw captures when no longer needed.

Maintenance record (2026-10-21, 0.1.26): authorized temporary capture implementation. Host verification covers exact IN/OUT/forwarded byte identity, one-shot no-overwrite, nonzero vendor exit/output, fail-open storage preflight, size-cap discard and 12 MiB simultaneous bidirectional traffic. Current worker verification: all seven capture tests and repository validation pass. The full suite cannot pass here: the metadata test class requires a C compiler that is absent; compiler/header-dependent checks are also skipped. Compiler-dependent validation remains required in the Debian build environment. No HAOS deployment or physical print is performed by development tooling.

# Release 0.1.25: first raster header at the HP boundary

Diagnostics only. The 0.1.24 AirPrint PDF path now completes through pdftopdf,
Ghostscript, rastertospl and the backend, but physical color output has a regular
line/raster artifact even with neutral HP vendor settings. This release collects
the missing header evidence; it does not identify or correct that artifact.

The SHA256-pinned ARM64 HP ULD ELF imports the legacy `cupsRasterReadHeader`
symbol from the dynamic CUPS libraries. The new build-time compiled
`scripts/raster-header-diagnostics.c` shared library is preloaded **only into
the supervised rastertospl child**, via `scripts/job-stage.py`. Python, USB,
Ghostscript, pdftopdf and PAPPL do not receive this preload.

The legacy CUPS header omits cupsNumColors. The shim calls the public extended
`cupsRasterReadHeader2` once on the existing stream, then copies the exact
legacy prefix into HP's caller-provided header. Both installed Debian CUPS APIs
call the same internal decoder exactly once, then copy their respective header
or zero it on failure; disassembly was checked during implementation. Compile
assertions guard the unsigned width and prefix ABI. This retains the existing
decoder, raster handle, stdin/file descriptor, header contents, return status
and errno, including failure/EOF zeroing. It does not open another raster reader,
read pixels, consume a second header, proxy stdin, replay bytes or create files.
No proprietary binary, library, CMS or PPD is patched.

After the first successful header only, the shim attempts one fixed numeric
record write to the existing supervised stderr. The record fits a 256-byte
stack buffer even with every field at UINT32_MAX; it is never retried. The
supervisor accepts only the exact versioned record with 14 unsigned 32-bit
decimal fields, using its existing 256-byte line bound. It reconstructs one
INFO message per invocation and discards all other vendor text as before.
A malformed/overlong record, missing header or unsuccessful diagnostic write
produces no header line and does not reject or retry printing. Header strings,
page-size names, filenames, options, environment, credentials and image data
are never logged. Vendor stderr cannot inject arbitrary text through this path.

Fields are width, height, xdpi, ydpi, cupsBitsPerColor, cupsBitsPerPixel,
cupsNumColors, cupsBytesPerLine, cupsColorSpace, cupsColorOrder and
cupsCompression. cupsRowCount, cupsRowFeed and cupsRowStep are also reported as
numeric context. Values are **decoded by CUPS**, including its legacy-format
defaults, rather than a raw wire-header dump. Numeric color-space/order enums
are retained without guessing a textual interpretation.

`expected_bytes_per_line = (width * cupsBitsPerPixel + 7) // 8` uses
overflow-safe Python integer arithmetic. `packed_relation=equal|above|below`
compares the actual count with this packed reference. This is not a validation
error: padding and banded/planar color layouts can change the interpretation
of a line, and row/band controls or physical page dimensions must not be
confused with raster pixel width. No assertion, setting change or job failure
depends on this calculation.

Illustrative sanitized line (fixture values, not a physical print observation):

```text
INFO: path job=7 stage=rastertospl raster-header page=first width=13 height=3 xdpi=600 ydpi=600 cupsBitsPerColor=8 cupsBitsPerPixel=24 cupsNumColors=3 cupsBytesPerLine=39 cupsColorSpace=1 cupsColorOrder=0 cupsCompression=0 cupsRowCount=0 cupsRowFeed=0 cupsRowStep=0 expected_bytes_per_line=39 packed_relation=equal comparison_scope=packed-reference
```

Maintenance record (2026-10-13, 0.1.25): authorized diagnostics-only release,
with version metadata and changelog updated. Deterministic fixtures compare
instrumented versus baseline CUPS legacy headers byte-for-byte, pixel output,
return values and errno for two-page uncompressed v1, compressed v2, PWG,
RGB chunked/banded/planar and packed 1-bit inputs. Empty/corrupt/truncated input,
named-file input, suppressed stderr, single decoder invocation, prefix ABI,
failure zeroing, one-time logging, UINT32_MAX arithmetic, fragmented/malformed/
overlong records, redaction, token scrubbing and stage scoping are covered.
An end-to-end fixture runs the actual shim through the supervisor, preserving
binary stdout and emitting only the reconstructed sanitized header line.

Verification: the full isolated Debian suite passed **116/116 tests**, including
all compiled real-CUPS fixtures. The host suite passed 111 tests with 5 CUPS-
dependent tests skipped because host development headers are absent; all five
ran successfully in Debian. Repository validator, Python compilation, all shell
syntax checks and git diff --check passed. The configured PAPPL1 compile/link
gate passed without executing its probe; the unchanged patched retrofit build
also passed. The shim compiled with -Wall -Wextra -Werror.

All 0.1.24 protections, PDF helper bounds, source pins, filter/backend chain,
HP assets, UID/GID/no_new_privs, persistence, mDNS, USB discovery/settling,
PAPPL1 gate, port 8631 and info default remain. No queue creation, print action,
settings change, HAOS deployment or CUPS2.4 repository access is performed.
The central maintenance log at /home/philip/lex-v2/runtime/maintenance.log
records this release separately.

Caveats: local compile/link and fixtures use x86_64 Debian/PAPPL1. The ARM64
vendor import was verified statically without execution; native ARM64/HAOS
loading and a manually initiated real-job trace remain runtime acceptance.
Only the first successful page per rastertospl process is logged. A future
vendor changing header API or a CUPS ABI change requires review of this shim.
The instrumentation preserves decoder semantics verified for the current
Debian libraries; no physical artifact diagnosis is claimed by fixture tests.

# Release 0.1.24: bound automatic PDF metadata detection

Root cause: the pinned upstream `_prGetFileContentType()` composes
`pdfinfo <filename> 2>/dev/null || exiftool <filename> 2>/dev/null`,
launches it with `popen(command, "r")`, consumes stdout through blocking
`fgets`, then calls `pclose`, with no deadline. The fresh 0.1.23 iPhone
trace reaches `metadata-launch phase=end` and `metadata-scan phase=begin`
but never scan end, metadata wait or filter-chain launch. This localizes the
observed stall to unbounded metadata stdout consumption/parsing, before the
conversion chain. The helper's internal reason for stalling is not established.

The narrow patch executes fixed `/usr/bin/pdfinfo` then optional
`/usr/bin/exiftool` with argv containing exactly the utility and the actual
absolute spool filename. There is no shell or filename interpolation. A
nonabsolute filename fails open rather than being interpreted as an option.
The parent retains the child PID, uses nonblocking read/poll and a monotonic
**2,500 ms deadline per helper**, including stdout consumption and waiting for
exit. At most 16 KiB is captured into a fixed stack buffer; NUL output or reaching
the cap rejects detection. Lines over 255 bytes are ignored without parsing
fragments. Stdin/stderr use /dev/null. No output is logged.

Timeout/read/overflow failure closes the pipe, sends SIGTERM, allows **100 ms**
for exit, escalates to SIGKILL if necessary and always calls waitpid to reap the
child. Polling continues to honor the deadline when stdout closes before the
child exits. Both helpers therefore have a nominal maximum combined budget of
**5.2 seconds**, plus OS scheduling and final SIGKILL/reap overhead; as with any
POSIX process, an uninterruptible kernel task can delay final reaping.

Only a successful helper exit with recognized Producer/Creator/Creator Tool
metadata chooses a content optimization. pdfinfo has first preference;
failure, missing utility or no recognized creator tries exiftool once.
Both failures, timeout, malformed/empty output or no recognized creator return
`PAPPL_CONTENT_AUTO`; metadata detection cannot reject the print job.
The upstream creator arrays and content mappings are retained. Word-boundary
matching safely handles a name at the start of a value and always advances
after a nonmatching embedded substring, avoiding the upstream parser's
before-string read and nonadvancing search. JPEG/PNG behavior is unchanged.

The entire upstream metadata function is checked against a pinned reference
before replacement; drift fails the build before source writes. The reference
`scripts/pdf-metadata-upstream.c` is review input, never compiled. Docker stages
it and `scripts/pdf-metadata.h` alongside the patcher. Existing content-detect
and spooled callback/filter/backend diagnostics remain. Metadata launch/scan/wait
begin/end markers retain their order per helper, now enclosing fork,
nonblocking capture and reap. Added INFO labels are fixed/allowlisted:
`metadata helper=pdfinfo|exiftool`,
`metadata outcome=complete|helper-failure|bounded-failure`,
`metadata detection=recognized|auto`. All new logging preserves errno;
no filename, argv, environment, metadata or client value reaches it.
The obsolete raw metadata/filename DEBUG/WARN messages in this replaced
function are removed.

Maintenance record (2026-10-13, 0.1.24): approved metadata-only fix and version
bump. Deterministic compiled C fixtures verify exact argv with spaces and shell
metacharacters, pdfinfo success/preference, fallback, both missing/failing,
content mappings, unknown/empty/malformed/NUL output, large/no-newline output,
SIGTERM-resistant hangs, stdout-close-then-hang, deadline bounds, repeated
successful execution, no unreaped children, redaction, errno preservation and
marker order. Regression coverage verifies the entire spooled callback is
identical before/after metadata replacement. Full host and isolated Debian
suites each passed all 105 tests. Repository validator, Python compilation,
all five shell syntax checks, diff whitespace, configured PAPPL1 compile/link
and patched pinned retrofit library/application build passed against PAPPL 1.3.1.
The isolated validator used a pure-Python PyYAML check fixture under ignored
run-data; no application dependency or host package was changed.

All architecture, dependency pins, PAPPL1 compatibility, permanent privilege
drop, token scrubbing, persistent state, mDNS, USB, HP ULD, filters and backends
are preserved. No stable CUPS2.4 changes, HAOS installation, queue creation or
physical printing are part of this work. The central maintenance log is outside
repo scope and was not modified. The build gate is local x86_64/PAPPL1; a new
ARM64 image build and manually initiated iPhone trace remain runtime acceptance,
not claimed by these fixture/build checks.

# Release 0.1.23: localize the stall after spooled retrofit entry

The 0.1.22 iPhone trace reaches successful Send-Document completion and
`retrofit-entry mode=spooled`, then continues polling without downstream
markers. Inspection of the pinned `_prFilter` shows `papplJobCreatePrintOptions`
is the first operation after entry. `_prCreateJobData` follows, before the old
binding/accepted markers. In its automatic content optimization branch,
`_prGetFileContentType` already launches `pdfinfo`/`exiftool` with `popen`, scans
with `fgets`, and waits with `pclose`. This is an early subprocess, distinct
from the conversion filter chain, and a plausible blocking location.

All added messages have exactly `lifecycle stage=retrofit-<fixed-name>
phase=begin|end`, at INFO, with no runtime value interpolation. Every added
logger call saves/restores errno. The spooled callback boundaries are:

| Fixed stage suffix | Original operation enclosed |
| --- | --- |
| print-options | `papplJobCreatePrintOptions` (PAPPL1 option/raster setup) |
| job-data | `_prCreateJobData` (PPD and option mapping/filter data) |
| filter-data | `cfFilterDataGetExt` and PPD pointer acquisition |
| input-filename | `papplJobGetDocumentFilename` |
| input-open | Existing `open` condition and failure branch |
| format | Existing binding/allowlisted accepted log and document format getter |
| conversion | Conversion iteration / `_prPPDFindCUPSFilter`, existing rejection branch |
| ppd-load | `ppdFilterLoadPPD` |
| backend-connect | Existing conditional `papplDeviceGetData` and filter-data assignment |
| pdf-scan | Existing PDF-only `fdopen` / `getline` / `rewind` / line cleanup |
| chain-setup | Array creation, allocation and original chain assembly |
| status | First `_prUpdateStatus` before launching filters |
| impressions | `papplJobSetImpressions` |
| output-open | Existing `/dev/null` open |

Nested boundaries in the shared job-data/content helper are `content-detect`
(`_prGetFileContentType`), `metadata-launch` (`popen`), `metadata-scan` (the
existing conditional `fgets` scan and parsing), and `metadata-wait` (`pclose`).
Their original conditions remain intact; shared helper markers can also appear
for existing non-spooled callers. No reads, subprocesses, getters, stream
wrappers, temporary streams, command changes or runtime control logic were
added. This source has no additional temp/output stream setup in `_prFilter`.
The existing INFO `filter-chain started` immediately precedes `pocChain`, and
the older per-filter markers remain the downstream launch diagnostics.

The last begin without an end identifies the operation or bounded setup block
that has not returned. Input-open/conversion ends describe successful progress;
original early error returns bypass those ends. Conditional metadata/PDF markers
are absent when their original branches are skipped. Missing ends can also mean
process failure or logging failure, so they are evidence of location, not proof
of deadlock. Job-data outside content detection and PAPPL option creation remain
coarse library boundaries: one trace cannot identify their internal lock or
individual getter. Metadata-scan cannot distinguish waiting for child output
from parsing that output; metadata-wait isolates the child wait. No content,
paths, names, addresses, raw IPP values, environment, argv or errno text is added
to logs. Existing upstream messages and older diagnostics are untouched.

Maintenance record (2026-10-13, 0.1.23): expanded reviewed pinned source excerpts
cover the complete spooled callback and metadata scan. Four new regressions
check PDF-path marker order, identity of all original code after removing the
new markers (including conditions, read/launch counts and arguments), compiled
errno preservation with a logger that overwrites errno, and fail-closed anchor
drift without source writes. Full isolated Debian suite: 94 tests, all passed.
Repository validation, Python compilation, all five shell syntax checks,
`git diff --check`, configured PAPPL1 compile/link gate and compilation/linking
of the patched pinned retrofit library/application passed against PAPPL 1.3.1.
Dependency pins and all print, threading, retry, timing, spooling, USB, mDNS,
IPP and privilege behavior are preserved. Earlier 0.1.20/0.1.21/0.1.22 diagnostics
remain. No stable CUPS2.4 access, HAOS install, physical print or queue creation
was performed. The central runtime maintenance log is outside repository scope
and was not touched. A new manually initiated iPhone trace is still needed;
no live acceptance is claimed.

# Release 0.1.22: acquire logging options before privilege drop

The 0.1.21 startup order caused the reported failure: Docker starts the USB
bootstrap as root, which permanently drops to UID/GID 10001 before the shell
reads Supervisor-managed `/data/options.json`. Only `/data/state` is prepared
for the app identity. An unreadable options file therefore produced the fixed
invalid-options error immediately after the USB identity marker, even with
`log_level: info`. No live HAOS filesystem was inspected for this investigation.

The bootstrap now reads and validates server logging options before identity
setup/drop, reusing the exact PAPPL 1.3.1 allowlist (`fatal`, `error`, `warn`,
`info`, `debug`). It clears any inherited `POC_LOG_LEVEL` and exports only the
validated value. Missing standalone options/file or key still defaults to `info`;
malformed, invalid or unreadable options fail before setup/drop/app launch with
no input or exception disclosure. The shell accepts only that allowlisted env
value and never reads options. Drivers/validate modes retain their existing
behavior. Supervisor-managed `/data` and options ownership/mode are untouched.

The 0.1.21 schema/default, token scrubbing, USB groups, permanent identity drop,
`no_new_privs`, persistence, mDNS/AirPrint, filters/backends, INFO lifecycle
markers and `log-file=-` are preserved. No CUPS 2.4 service access/modification,
HAOS install, physical print or queue creation was performed.

Maintenance record (2026-10-13, 0.1.22): regression coverage exercises all five
levels across the bootstrap transition and real shell, deletes the options file
at the transition, checks simulated UID 10001 acquisition ordering, fail-closed
errors before setup/drop/exec, standalone defaults and unchanged INFO markers.
Host suite: 90 tests, 88 passed and two compiler-environment skips. Isolated
Debian suite: all 90 passed. Repository validation, Python compilation, all five
shell syntax checks, the explicit configured PAPPL1 compile/link gate and
`git diff --check` passed. Installed PAPPL is 1.3.1 and the retrofit checkout
matches the unchanged pin. Identity transitions in the regressions are mocked;
no live HAOS startup is claimed. The central runtime maintenance log is outside
the authorized repository scope and was not touched.

# Release 0.1.21: configurable PAPPL server logging

Set the add-on option `log_level` to `fatal`, `error`, `warn`, `info` or
`debug`. The default is `info`: current INFO lifecycle markers remain visible,
while PAPPL DEBUG polling is suppressed. Higher thresholds hide INFO markers;
select `debug` only when needed. This controls PAPPL server logging, not fixed
startup, filter/backend or private daemon diagnostics.

Verified against installed PAPPL 1.3.1 and its `pappl/mainloop-subcommands.c`
`log-level` parser: these five lowercase spellings are the supported values.
Pinned retrofit `49ad525a3715a57aae24c715ef0767b55ffb1991` delegates to
`papplMainloop` and uses that parser. No `warning`, `trace` or `none` alias is
exposed. In 0.1.21, `/data/options.json` was read after privilege drop; a missing file/key
uses `info` for standalone containers and upgrades. Invalid values, malformed
JSON, non-object options and unreadable files stop server startup with a fixed
error before driver staging or server launch. Input contents are never logged.

The selected allowlisted value is passed as one quoted `-o log-level=<value>`
argument; `log-file=-` remains unchanged. No shell evaluation or output filtering
is added. All 0.1.20 print behavior, AirPrint/IPP, USB/filter/backend chain,
persistence, security, mDNS, PAPPL1 compatibility and source pins are preserved.
No HAOS install or physical print is part of this release validation.

Maintenance record (2026-10-12, 0.1.21): host suite 86 tests passed (two
build-environment skips); isolated Debian suite all 86 passed, including the
PAPPL1 compile/link gate. The explicit configured retrofit compatibility gate,
`validate_repository.py`, Python compilation, all shell syntax checks and
`git diff --check` passed. Installed PAPPL reports 1.3.1 and the retrofit checkout
matches the unchanged pin. No HAOS install or physical print was performed.
The central maintenance log was not available in this workspace; this repository
record contains no secrets.

# Release 0.1.20: diagnostics-only pre-retrofit boundaries

This candidate preserves working 0.1.19 print behavior. No cause of the iPhone
processing/job-printing stall with zero impressions has been proven. The added
INFO records locate a stop before retrofit dispatch; they do not fix one.
No automatic jobs, new queues, retries, deadlines, reads or scheduling changes.
PAPPL 1.3.1, retrofit/libppd pins, advertising, security, persistence, device/USB
handling, submission, transport and filter/backend chain remain unchanged.

The existing fail-closed PAPPL patch now validates every exact-source anchor and
the absence of its generated header before writing any source. The header contains
only fixed-label metadata helpers and an errno-preserving INFO macro. There is no
read-observation wrapper: raster-open and first-header boundaries suffice to locate
which original call is blocked. No per-read/page diagnostics are added.

Added marker names and locations (all `lifecycle stage=`):

| Stage | Location / values |
| --- | --- |
| `ipp-submission begin` | Decoded Print-Job/Create-Job/Send-Document, before validation; request id, fixed operation, supplied format and compression |
| `ipp-last-document` | Send-Document only at decode; present/valid/value booleans, invalid value logged as 0 |
| `ipp-data begin/result` | Existing document-presence probe; begin before original httpPeek, result present boolean; non-receive state emits result=0 without a peek |
| `ipp-submission returned` | After operation returns, before trailing-data flush/HTTP response; response job id, request id, fixed operation and status class |
| `document-effective` | Accepted document receipt before streaming/spooling selection; request id, operation, effective job format; existing papplLogJob prefix supplies job id |
| `document-branch` | Before raster dispatch or spool file creation; streaming-raster/spooled-non-raster |
| `processing-set` | Immediately after original processing state assignment |
| `device-availability begin/result` | Before existing availability check / after wait, before existing open loop; in-use boolean, available/unavailable/deleted/canceled |
| `raster-open begin/result` | Around original cupsRasterOpenIO; success/error |
| `raster-first-header begin/result` | Around original first cupsRasterReadHeader; success/error |
| `print-options begin/result` | Around first streaming and raw PAPPL options creation; streaming/raw and nonnull boolean |
| `print-dispatch begin/returned` | Immediately around original filter, printfile or rstartjob callback; fixed callback enum and returned success boolean |
| `document-receive result` | After existing spool read loop; eof/error, before close |
| `spool-close begin/result` | Before existing close, failure branch or successful close; success/error |
| `spool-submit begin/returned` | Around original file submission; returned means function returned, not that printing completed |

Existing `document-receipt`, `document-spool`, `registered`, `scheduler-check`,
`scheduler-launch`, `execution`, `device-wait`, first-attempt `device-open`,
`device-ready`, `document-stream`, and `retrofit-entry` markers remain. After a
failed first open, `device-ready` distinguishes eventual availability from exit;
there is no added device retry logging or retry behavior. Filter callback options
are created inside retrofit, whose existing entry marker precedes that work.

Formats: pdf, urf, pwg-raster, jpeg, png, postscript, octet-stream, other, unknown.
Compression: none, gzip, deflate, compress, other, unknown. Absent/mistyped supplied
metadata is unknown. These are labels, not MIME/compression acceptance rules.
Status class: success, other, client-error, server-error. Numeric correlation is
bounded to 0..INT_MAX; 0 means unavailable/nonpositive. Job-prefixed logs use the
existing numeric PAPPL job prefix. No new names, URIs, identity, title, filenames,
attributes, document contents, user-agent or raw errors are logged. Existing
upstream logs are unchanged. An acceptance/result line alone does not prove a
successful print, and a missing return line identifies a boundary, not a cause.

Manual HAOS validation (operator only; not performed during repository work):
restart the addon to clear the log, begin saving the full log before submission,
submit exactly one iPhone print, and save through stall or completion. Locate
request/job correlation, then the last begin/result pair through device readiness,
raster open, first header, options, callback and existing retrofit/filter/backend
markers. Record job state and impressions. If possible repeat separately with one
known-good Windows job and compare paths. A blocked open/header call may reflect
partial or interrupted input; an error/cancel path should retain original ordering.
Do not submit automatic diagnostics jobs. Redact existing upstream identifiers and
secrets before sharing logs; retain the original full log locally.

Maintenance record (0.1.20): reviewed pristine PAPPL 1.3.1 source from the existing
Debian source archive; extended only the existing diagnostics patch, source excerpts,
regression tests, version metadata and release documentation. No AGENTS.md exists
in the checkout or applicable parent path. No stable CUPS2.4 repository touched.
Validation: all 81 tests passed in the prepared Debian environment (no skips),
including six new boundary tests and all 75 existing tests. Host: 81 tests, two
compiler-dependent skips. Final pristine PAPPL 1.3.1 with both repository patches
configured and built successfully; only existing unrelated upstream/compiler and
make jobserver warnings were observed. The PAPPL1 compile/link gate passed with
the candidate library on the compiler search path; its probe was not executed.
Repository validator, Python compilation, five shell syntax checks and git diff
whitespace checks passed. A temporary executable probe was placed inside the
repository because the prepared environment's /tmp is noexec; it used synthetic
metadata and read-return stubs, never real jobs or device IO. Build/test logs stay
in ignored run-data. No HAOS installation, physical print, ARM64 image build or
live-runtime diagnosis is claimed.

# Release 0.1.19: persistent queues and USB settling

Queue loss was caused by `STATE_DIR=/work/state` on the disposable container
filesystem. `STATE_DIR=/data/state` now covers both the PAPPL app state and
retrofit installable-option configuration. PPD paths remain `/work/state/ppd`;
the baked-in HP PPD and generated runtime assets keep their startup behavior.
Spool and capture remain ephemeral. No print/filter/backend code changes.

Before dropping privileges, bootstrap prepares only `/data/state`, rejects
symlink directories and assigns 0700/10001:10001 only when needed. It never
recursively changes `/data`. After token removal and privilege drop, migration
retains existing persistent state; otherwise it copies only
`legacy-printer-app.state` and `p[0-9]{5,10}-inst-opt.conf` from retained legacy
state. Bounds: 256 directory entries, 64 files, 1 MiB/file, 8 MiB total.
Nonregular files/symlinks fail closed. Inputs are validated before publication;
fsynced temporary files are linked without overwrite, app state last, then the
directory is fsynced. Sources remain intact. Interrupted partial migration can
retry without replacing configuration. Failure prevents a misleading empty app.
No recovery is possible from already discarded legacy state: export before the
first upgrade and restore only configuration with owner 10001:10001. See README.

USB startup was a single diagnostic snapshot despite confirmed delayed visibility.
`usb-settle.py` now runs after existing diagnostics and before server launch under
the final identity. Six attempts call `/opt/poc/backend/usb` without job arguments
and retrofit `devices`, each through the existing bounded 32 KiB/eight-second
probe. Only successful retrofit HP enumeration marks readiness. Backoff is
2/4/8/16/16 seconds, totaling a maximum 142-second probe/backoff budget; preexisting
diagnostics/preparation are additional. Ready stops early, exhausted or failed
still launches the server. No retries affect printing. Discovery may claim USB
interfaces through existing CUPS behavior; no added resets/unbinding or privilege
changes. Late hotplug/settling beyond the bound still requires refresh.

New INFO records: persistence `fresh|migrated|retained`, writable boolean,
USB attempt 1–6, visibility `visible|unconfirmed`, fixed backoff seconds and result
`ready|exhausted|failed`. Errors are fixed labels. No raw backend strings, device
URIs/serials, user/queue identities, filenames, environment or credentials are
logged by these changes. Existing upstream debug logging is unchanged.

Maintenance record (0.1.19): startup state/discovery inspection against the pinned
retrofit and PAPPL 1.3.1 source; scoped persistence bootstrap/migration, bounded
discovery helper, regression/static checks, metadata and documentation updates.
No AGENTS.md exists in the checkout/parent path. Independent read-only review approved the final implementation with no blockers.
Validation: all 75 tests passed in the prepared Debian build environment (no
skips); the host run passed with one compiler-dependent skip. The real PAPPL1
compile/link gate passed against libpappl-dev 1.3.1-2.1 without executing its
probe. Repository validation, Python compilation, shell syntax and diff whitespace
checks passed. No ARM64 image build or live HAOS/hardware result is claimed. PAPPL/libppd/retrofit selections,
allowlist capture,usb, USB mapping, UID/GID/no_new_privs, token removal, private
mDNS and IPP-only/no-TLS remain unchanged. No HAOS install or physical print occurs.

Hardware acceptance: preserve/restore old config before upgrade, verify the same
queue and settings after two restarts/container replacement, observe bounded USB
readiness and Add Printer visibility, test disconnected startup and capture,
and verify IPP-only/mDNS/security regressions. Physical printing already worked
on 0.1.18; any new page must be manually authorized/submitted by the operator.

## Historical 0.1.18 lifecycle diagnostics

Version **0.1.18** adds INFO `lifecycle stage=...` markers only. The existing
Debian PAPPL **1.3.1** selection, libppd pin, retrofit commit
`49ad525a3715a57aae24c715ef0767b55ffb1991`, PAPPL1 compatibility gate,
AirPrint/USB/IPP/TLS policy, saved queues and filter/backend chain are retained.
No automatic printing, retries, deadlines, document copies or persistence changes
are introduced. PAPPL's existing device retry/wait behavior is retained.

Markers cover:

- `startup`: fixed release/diagnostics marker before application launch; this is
  not proof that the application has started successfully.
- `ipp-decoded`: numeric operation code, restricted to Print-Job (2), Create-Job
  (5) and Send-Document (6), before request validation. No client logger is used.
- `job-create`: begin, capacity/allocation failure or success, numeric queue ID,
  initial job state and reason bitmask. This includes restored/internal jobs;
  the initial held state does not imply a user-requested hold.
- `document-receipt`: begin, fixed processing/hold-new rejection or abort;
  `document-spool`: start, first successful write and completed byte count using
  the existing counter. Zero-byte documents have no first-write marker. Spool
  completion is after successful close and before submission.
- `registered`: spooled pending/held state with reason bitmask and fixed
  `ready|hold-new|hold-until` labels; streaming pending state before execution.
- `scheduler-check`: one submission-time snapshot with fixed
  `device-in-use|processing|deleted|stopped|check` labels. This is a snapshot,
  not a definitive later scheduler outcome. `scheduler-launch` records begin and
  thread creation success/failure on actual launches. The child can log execution
  before the parent logs successful launch.
- `execution`: spooled/streaming entry; `document-stream complete` records the
  streaming cleanup state before existing job finalization, including aborts.
  It does not claim successful printing.
- `device-wait`: one availability-wait entry; `device-open`: first attempt begin
  and boolean result; `device-ready`: final boolean availability with fixed
  `available|deleted|canceled|system-stopped` reason. Reused devices have no open
  marker. Later retry attempts emit no new markers, so repetitive waits are bounded.
- `retrofit-entry`: earliest safe spooled, streaming and raw callback entries,
  before the existing 0.1.17 binding and backend records. Raw entry follows the
  existing null job/device guard. Streaming entry is in shared raster preparation.

New records contain only numeric IDs/codes/states/bitmasks/bytes and fixed enum
labels. Job logging uses PAPPL's numeric job prefix. Queue creation records use
`papplLog` and numeric queue IDs because `papplLogPrinter` includes a queue name.
No new record includes identity, address, URI, names, filenames, user agent,
arbitrary attributes, environment, secrets or raw errors. Existing upstream
logs remain unchanged and can contain sensitive data: share only sanitized
lifecycle/path records after reviewing surrounding output.

Intentionally omitted: streaming first-write and input byte totals (PAPPL's
raster reader does not expose a counter without wrapping its I/O); per-retry
open results and periodic scheduler defer/held enumeration (would need diagnostic
state to bound repeated logging); per-stage elapsed time; detailed spool abort
errno/partial byte totals; a separate wait-exit marker (final availability is
reported by `device-ready`). No speculative interception or state fields added.
IPP records before job creation have no job/queue association yet.

Files changed: `Dockerfile` wires the guarded lifecycle patch into the existing
Debian rebuild and bumps the version; `config.yaml` bumps the release;
`scripts/entrypoint.sh` adds startup; `scripts/patch-pappl-lifecycle.py` adds
PAPPL markers with all anchors checked before any source write;
`scripts/patch-job-path.py` adds only retrofit entry logs; `tests/test_lifecycle.py`
and six files under `tests/fixtures/lifecycle/` exercise reviewed source excerpts,
marker presence/order, fixed-value redaction, repeat rejection and source drift;
this document and `CHANGELOG.md` record the release. Fixtures are source excerpts,
not runnable source or print documents. PAPPL excerpts are from Debian's
`pappl_1.3.1.orig.tar.gz`; retrofit excerpts are from the pinned commit above.

Local validation for this change: 64 unittest cases ran, 63 passed and the
existing compiled binding-classifier regression skipped because no C compiler
is installed. Python compilation, shell syntax and tracked/new-file whitespace
checks passed. Both patchers applied successfully to complete reviewed original
sources as well as the stored excerpts. No Docker executable, C toolchain,
ARM64 runtime, HAOS host, iPhone or printer is available here; the image/package
build, compatibility compile/link gate execution and live acceptance were not
run. Tests use fake children/capture fixtures and submit no physical print job.

Host review: review the uncommitted diff, build the ARM64 image and confirm the
installed release/startup marker before any separately authorized manual print.
Local tests and source patch application do not prove hardware printing or
AirPrint operation. Do not infer a fixed stall or successful page from markers.

---

Version **0.1.17** also logs `path binding=cups:usb|usb|capture|other|invalid`
at each existing job start. The USB wrapper reports the fixed executable path,
class, argument count (excluding argv[0]), and `normalized-usb=true|false` from
the actual child environment before launching the real backend. Invalid URI,
argument count or job ID yields `reason=invalid-usb-invocation` without launch
or retry. Discovery logs binding classes instead of full device URIs. No URI,
serial, options or client identity is included in these records. A `usb` queue
binding may use PAPPL's native transport, so absence of a CUPS USB launch record
is useful evidence. Queue persistence remains outside this release.

# Experimental HP150 PAPPL PoC

Version **0.1.17** adds bounded diagnostics for the physical job path while
preserving 0.1.15 AirPrint/mDNS, plain IPP on 8631, USB bootstrap, capture,
token scrubbing and Protection mode. No queues or jobs are created or deleted.

The pinned retrofit has distinct spooled PDF and streaming raster paths. New
fixed-label `path` records show job format (`urf`, `pwg-raster`, `pdf`, etc.),
source (including native raw bypass), numbered filter stages, chain exit status, first backend write and final
bytes handed to PAPPL's device, plus read/write errno on failure. Numbered stages
follow conversion order; the last stage is the backend handoff. The HP filter and
USB backend additionally report numeric job ID, invocation, exit, timeout and
fixed vendor markers (open, claim, write, timeout, permission, busy, CMS), with
numeric libusb codes when observed. Markers describe observed stderr terms;
`write` or `cms` alone does not prove a failure. No new diagnostic records expose
document bytes, titles, user names, options, USB serials, paths from clients or
secrets. Vendor stderr is drained with bounded memory and replaced with these
labels; known CUPS `STATE` protocol labels are preserved. Binary stdin/stdout and
inherited CUPS back/side channels are unchanged. Capture storage is unchanged.

Each HP filter/USB invocation has a **180-second wall-clock deadline**, kills its
process group on expiry, reports failure, and adds no retries. Cancellation is
forwarded to the child group. This bounds waits inside those executables; it is
not a global deadline for PAPPL document receipt or all upstream conversions.
A timeout may occur after partial physical output. Do not automatically resubmit;
inspect printer/output and cancel pending work manually before another test.
Native USB transport behavior, including its existing internal recovery, remains
unchanged. Handoff bytes mean bytes delivered into the device path, not confirmed
physical pages; backend success also needs the physical-page gate.

**Diagnosis: diagnostics-only.** Source inspection confirms previously discarded
streaming-chain and backend close statuses, but cannot prove the observed HAOS
stall's cause. No format conversion, queue, USB transport or backend sequencing
fix is claimed. The new stage boundaries distinguish receipt/conversion stalls
from vendor filtering, data handoff, backend shutdown and USB errors.

### HAOS acceptance for 0.1.18

1. Preserve the existing physical USB queue with the state export/restore procedure
   below; `/work/state` is container-local and may disappear during rebuild. Stop
   the PoC after manually draining/cancelling pending jobs. Leave the CUPS2.4 app
   untouched. Never restore spool/jobs or create/delete a queue for this upgrade.
2. Reload the store (`ha store reload`), update this PoC to **0.1.18**, or rebuild
   if already installed. Verify installed version 0.1.18. Keep Protection mode
   enabled, startup manual and port 8631. Restore only saved state with ownership
   10001 if needed, then start and verify the same queue, driver and USB URI.
3. Verify the USB access diagnostics and the physical queue's resolved AirPrint
   record, `advertisement=ipp-only`, security `none`, port 8631, and no TLS/IPPS.
   Startup must not submit a job. Get-Printer-Attributes alone is not acceptance.
4. With the printer idle, **manually** submit exactly one built-in test page to
   that queue. Require one correct physical page and correlated job logs: spooled
   format, all stages finish with exit 0, rastertospl exit 0, nonzero handoff bytes,
   USB/backend exit 0, no timeout and completed job. Do not submit the iPhone test
   while this job is pending.
5. Manually submit one known one-page iPhone document to the same discovered
   queue. Record its job ID and actual accepted format/source; require every
   numbered stage to finish, HP/USB exit 0, nonzero bytes, completed job and one
   correct physical page. `job-impressions-completed=0` plus IPP acceptance is
   insufficient. If stalled, wait for the bounded external deadline and retain
   sanitized `path` records and job state. Identify the last started/unfinished
   stage; do not resubmit automatically. Remove client identity/title/URI or
   document information from any older PAPPL debug lines before sharing logs.
6. Optionally verify an **existing** capture queue with one manual job and its
   capture PASS result. Do not create a queue as part of this release validation.

Local verification: 51 unit tests pass, repository validation, shell syntax,
Python compilation and whitespace checks pass. The guarded patch applies to the
exact pinned retrofit and rejects reapplication. No ARM64 compiler/container
runtime or HAOS USB hardware is available here; image build and physical gates
above remain required. No print jobs were submitted during development.


Version 0.1.15 fixes TLS selection for this credential-free PoC. Startup adds
`server-options=no-tls`: PAPPL advertises plain IPP on **8631**, omits IPPS
printer/system services and printer URIs, and reports `uri-security-supported=none`.
The matching Debian PAPPL package is rebuilt with a narrowly checked patch to
omit its otherwise unconditional `TLS=1.2` TXT key in both DNS-SD implementations.
TLS stays disabled in this PoC; enabling it in a future release requires actual
server credentials and a verified TLS listener before advertising IPPS/TLS.
The 0.1.14 private Avahi ownership/hostname fix and all USB/security paths remain.
Bounded read-only discovery diagnostics report `advertisement=ipp-only`,
`unexpected-tls`, or `unconfirmed`, plus URI/security policy. Registration success
requires resolved AirPrint records and no observed local IPPS/TLS advertisement.
No startup queue creation or job submission is added. Existing container-local
state preservation instructions below still apply when updating the app.

Version 0.1.14 fixes the private Avahi startup failure in 0.1.13. Avahi's
`make_runtime_dir()` checks the compiled-in `avahi` user/group even with
`--no-drop-root`; 0.1.13 owned `/run/avahi-daemon` by `poc`, whose UID/GID
were different. Its attempted chown failed after the privilege drop and its
ownership check aborted startup before D-Bus hostname queries could work.
`hostname=unavailable` was a consequence, not an invalid HAOS hostname.

The private image now gives the Avahi account the same numeric UID/GID 10001
as `poc`. Bootstrap prepares only `/run/avahi-daemon` for a fresh `/run` tmpfs
before dropping privileges; discovery setup failure still permits USB startup.
The existing explicit `hp150-poc` hostname additionally disables machine-ID
selection. Host networking, private D-Bus and UDP 5353 coexistence are unchanged.
Bounded stderr collection emits fixed sanitized failure reasons, never raw output.
Registration success still requires resolved `_ipp._tcp` AirPrint subtype records
from the private instance with its effective hostname, LAN address, port 8631,
`rp`, `image/urf` and `URF`; both private processes must still be alive.
No queues or jobs are created by this update. A restart with no saved manual
queue correctly reports `registration=unconfirmed`.

## AirPrint/Bonjour release 0.1.15

The user has confirmed a real test page from the 0.1.12 manual PAPPL USB queue
on HAOS. This release repairs discovery for that proven path. Physical USB printing
is a regression gate: do not accept this release on the target until the same
queue still prints one manually submitted test page correctly. There are no
queue-creation, queue-deletion, migration or print-job commands in startup.

### Implementation and network access

PAPPL already generates each queue's IPP DNS-SD records, `_universal._sub._ipp._tcp`
AirPrint subtype, `rp`, `pdl` and `URF` capabilities. We do not publish a static
service that could lie about a queue or replace PAPPL's registration. Debian's
Avahi daemon/utilities and a private D-Bus are the minimal missing runtime
components. Both launch **after** the existing supplementary-GID/UID/GID 10001
and `no_new_privs` bootstrap. Tokens are removed before every launch. Avahi's
`--no-drop-root --no-chroot --no-rlimits` disables operations requiring privilege;
it does not give it root: it already runs as `poc`. Only its container-local
runtime directory is owned by `poc`; USB nodes are untouched.

`host_network: true` is the only new HAOS access setting. The bridge and a TCP
port publication cannot put link-local UDP 5353 multicast onto the LAN or make
container-address records usable by an iPhone. Sharing the host network lets
Avahi join the LAN interfaces and advertise host addresses. HAOS has no narrower
per-port multicast-join setting. This also exposes host interfaces to this PoC;
keep Protection mode enabled. No `privileged`, `full_access`, `host_dbus`,
`host_pid`, `host_uts`, extra capabilities, device mappings or AppArmor bypass is
added. The existing `usb: true` stays unchanged. A host-bus socket mount would
grant broader host access; an mDNS reflector would need additional network
infrastructure and could still advertise unusable bridge addresses.

PAPPL still listens on TCP **8631**, now with `server-options=no-tls`. Existing
port metadata stays for UI/watchdog compatibility, but host networking bypasses
Docker port translation: do not change the advertised port using a Network mapping.
The host must have no other listener on 8631. The private Avahi hostname starts
as `hp150-poc.local`; Avahi can rename it on collision, and diagnostics report
the effective hostname. It permits coexistence with HAOS's mDNS stack, enables
no reflector and publishes no workstation/HINFO/DNS-server records. Host Avahi
must also permit UDP 5353 sharing; a stack that binds exclusively is a deployment
blocker, not a reason to disable host services or grant privileges.

Sources: [HAOS networking configuration](https://developers.home-assistant.io/docs/apps/configuration/),
[PAPPL supported mDNS implementations](https://www.msweet.org/pappl/pappl.html),
[PAPPL 1.4.6 queue registration](https://github.com/michaelrsweet/pappl/blob/v1.4.6/pappl/dnssd.c),
[pinned retrofit AirPrint bootstrap](https://github.com/OpenPrinting/pappl-retrofit/blob/49ad525a3715a57aae24c715ef0767b55ffb1991/pappl-retrofit/pappl-retrofit.c),
and [Avahi daemon implementation](https://github.com/avahi/avahi/blob/v0.8/avahi-daemon/main.c).
The image records its actual Debian package versions for target verification.

### Preserve existing queues before update

`/work/state` remains container-local, exactly as in 0.1.12. Supervisor update or
rebuild may replace that filesystem. A normal add-on backup of `/data` does not
preserve it. **Export state before update if existing queues must survive.**
Do not uninstall, delete queues, or recreate them to perform this test.
Export `/work/capture` separately if you need its evidence. Drain/cancel any
pending jobs manually first; do not restore spool/jobs for this release test.

With an already available HAOS host/debug shell (these are host commands, not
commands inside an ordinary SSH add-on), run `ha addons list` and find the full
slug ending in `_cups3_hp150_poc`. Set it explicitly using the value shown:

```sh
POC_ADDON_SLUG='<full PoC slug from ha addons list>'
ha addons stop "$POC_ADDON_SLUG"
mkdir -p /mnt/data/hp150-poc-0.1.12-backup
test ! -e /mnt/data/hp150-poc-0.1.12-backup/state
docker cp -a "addon_${POC_ADDON_SLUG}:/work/state" /mnt/data/hp150-poc-0.1.12-backup/state
docker cp -a "addon_${POC_ADDON_SLUG}:/work/capture" /mnt/data/hp150-poc-0.1.12-backup/capture
```

Verify that the exported `state` contains PAPPL's saved configuration and retain
the exact existing queue name, driver and USB URI privately. Keep this backup
until physical and iPhone gates pass. If host access is unavailable, obtain a
state export before updating; a rebuild cannot be promised to preserve `/work`.
No host-shell access or container privileges are added by this release.

### Exact HAOS update/rebuild/start procedure

1. Leave `haos-cups-hp150` repository, configuration and queues untouched. Ensure
   the printer is idle and no other application submits jobs during this test.
   Complete the state export above and leave the PoC stopped.
2. Open **Settings → Apps/Add-ons → App/Add-on store → ⋮ → Check for updates**.
   Refresh the store if necessary. Open **HP 150 CUPS 3 Retrofit PoC (USB test)**
   and select **Update** when **0.1.15** appears. This source-only repository
   builds locally on ARM64; wait for successful completion. If 0.1.15 is already
   installed but the image is stale, use its **⋮ → Rebuild** instead. Do not
   uninstall/reinstall. Verify installed version **0.1.15**.
   CLI equivalent: `ha store reload`, then `ha addons update "$POC_ADDON_SLUG"`;
   for an already installed release use `ha addons rebuild "$POC_ADDON_SLUG"`.
3. Keep **Protection mode** enabled and startup manual. TCP 8631 is fixed under
   host networking; no port translation setting changes it. Keep the HP connected
   and powered on. Click **Start**, wait for the initial startup, then **Stop**
   if the replacement container needs the saved state restored. An empty new
   container advertises no printer queue and submits no jobs.
4. In the existing host shell, restore the saved state into the stopped replacement
   container, preserving its numeric ownership (10001). Do not restore spool:

   ```sh
   docker cp -a /mnt/data/hp150-poc-0.1.12-backup/state/. "addon_${POC_ADDON_SLUG}:/work/state"
   ha addons start "$POC_ADDON_SLUG"
   ```

   If the original state survived, use it directly; no restoration is needed.
   Confirm the existing queue's identity, driver and URI in the Web UI before
   any submission. If it is absent or different, stop and inspect the export;
   do not automatically create a replacement queue.
5. Check **Logs** for unchanged USB identity/access/allowlist diagnostics,
   `POC_PORT=<8631>`, `mDNS: private-dbus=running`, `mDNS: avahi=running` and
   `mDNS: registration=success service=<existing USB queue name> ... port=8631`.
   A success for only the capture queue does not prove the USB queue is advertised.
   `Unable to initialize DNS-SD: Daemon not running` must be absent. Startup
   waits at most 5 seconds for the private bus, 10 for Avahi, then approximately
   30 for registration; probe output is capped at 32 KiB. It logs at most 16
   resolved LAN service names, never raw TXT, credentials or environment dumps.
   No queue or daemon failure triggers a print job. If mDNS fails, PAPPL remains
   available for manual USB printing; TCP watchdog alone cannot validate AirPrint.
6. Open `http://<HAOS-LAN-IP>:8631/`. On the **existing physical USB queue**,
   manually submit **one Print Test Page**. Require successful job completion
   and a readable physical page with expected colors. This must pass before
   proceeding to iPhone. Capture QPDL PASS alone is insufficient.

For a bounded read-only recheck after a manual queue change, from the existing
host shell run (inside the running PoC as its restricted user):

```sh
docker exec --user 10001:10001 "addon_${POC_ADDON_SLUG}" python3 /opt/poc/scripts/mdns-runtime.py --diagnose
```

This uses the existing private bus, queries records for five seconds at most,
and submits no jobs. `registration=unconfirmed` is not success; check PAPPL's
registration logs, queue presence, AirPrint TXT fields and LAN interfaces.

### Precise iPhone/iOS test

1. Connect the iPhone to the same LAN/Wi-Fi segment as HAOS; avoid guest Wi-Fi,
   client isolation and VPN routing. Open `http://<HAOS-LAN-IP>:8631/` in Safari
   to verify IPP/HTTP reachability first.
2. In **Files**, open a known, single-page PDF. Choose **Share → Print → Printer**
   (or **Select Printer**). Wait up to 30 seconds. Select the name reported for
   the **physical USB queue**, normally `hp150-usb-test`. PAPPL can also advertise
   capture queues; selecting one produces captured output rather than a page.
3. Set **Copies: 1** and a one-page range. Confirm the selected printer, then
   tap **Print** once. Check **Print Center** via the app switcher while active.
   Require successful PAPPL job completion and one correctly rendered physical
   page; no duplicate submissions while waiting.
4. Record release version, effective hostname/service/8631 diagnostic line,
   iOS version, selected queue, job result and physical page result. Share only
   sanitized logs. If discovery fails but Safari works, inspect multicast; if
   discovery works but the job fails, inspect IPP/job/filter/backend diagnostics.
   A failed USB regression or iPhone print is a failed deployment gate.

Allow TCP 8631 and UDP 5353 multicast to `224.0.0.251` (IPv4) and `ff02::fb`
(IPv6). Bonjour is link-local; routed VLANs require a deliberately configured
mDNS gateway plus reachable advertised host addresses and TCP 8631. This PoC
supplies no gateway/reflector. Firewall, AP multicast suppression, exclusive host
mDNS bindings and IPv6 routing can prevent discovery. PAPPL's HTTP interface and
IPP are exposed on host interfaces; use a trusted LAN. AirPrint compatibility
is supplied by PAPPL's actual queue capabilities, not certification of this PoC.

### Validation and limits

The 36 local tests pass, including existing capture/USB/filter/token/GID tests
and new bounded-probe, AirPrint record validation, credential-free daemon order,
nonfatal daemon failure, cleanup and private D-Bus policy checks. Repository
safety/version checks, Python compilation, shell syntax and diff whitespace pass.
The USB bootstrap, both backends, ULD staging/wrapper and pinned source patches
are unchanged from 0.1.12.

A local non-root dependency and runtime-wrapper smoke test with `no_new_privs`
reached Avahi RUNNING over the private
D-Bus and registered/resolved a fixture `_ipp._tcp` service with the AirPrint
subtype and TXT fields. It used Alpine x86_64 binaries with runtime paths/user
relocated for this restricted workspace; it is **not** the Debian ARM64 image or
PAPPL/HP integration. No Docker daemon or target HAOS/iPhone hardware is available
here. The ARM64 image build, real PAPPL registration, host-stack coexistence,
physical USB regression and iPhone print must be verified with the steps above.
No automatic print jobs were run.



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

Historical pre-0.1.13: `Unable to initialize DNS-SD: Daemon not running` was expected because no
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

## Staged PAPPL1 compatibility gate

The Docker build now gates retrofit immediately after `./configure`, before
`make`: `python3 /tmp/check-pappl1-compat.py /tmp/retrofit`. The gate requires
`HAVE_PAPPL1=1` in the generated `config.h` and checks the pinned retrofit's
existing mappings of `papplJobGetDocumentFormat(job, doc)` to
`papplJobGetFormat(job)` and `papplJobGetDocumentFilename(job, doc)` to
`papplJobGetFilename(job)`. Source drift fails closed for review.

A temporary probe includes retrofit's actual `pappl1-private.h` and compiles and
links both document getter calls using the generated Makefile's compiler,
PAPPL/CUPS flags and libraries. The linked probe is never executed; it creates
no print job. Temporary probe files are removed. Dependency pins and release
version remain unchanged; this adds no lifecycle instrumentation.

Sandbox validation: `python3 -m unittest discover -s tests -v` includes gate
configuration/mapping rejection and build invocation tests without a compiler.
Those tests do not establish compiler/linker compatibility. Independent host
review, compiler validation and an ARM64 Docker build remain required before
any release decision.
