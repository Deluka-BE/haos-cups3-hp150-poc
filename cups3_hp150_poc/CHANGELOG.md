# Changelog

## 0.1.21

- Add validated `log_level` add-on option with PAPPL 1.3.1 supported values fatal/error/warn/info/debug; default info retains lifecycle markers and suppresses DEBUG polling.
- Pass the allowlisted value as a single server option, retaining log-file=-; fail safely on invalid/malformed options without input disclosure.
- Preserve all 0.1.20 print/runtime behavior and pins; add option/schema, rejection, argument and lifecycle regressions. No HAOS install or physical print.

## 0.1.20

- Diagnostics-only: bracket IPP acceptance/data presence, effective format, streaming/spooled selection, processing/device availability, raster open/first header, options and callback dispatch, spool close/submit.
- Fixed allowlisted INFO metadata, numeric request/job correlation, Send-Document last-document booleans; no raw document/device/user strings. Exact-source anchors fail closed; new logs preserve errno.
- Preserve 0.1.19 behavior, print chain and source pins. No extra reads, read wrapper, retries, deadlines, queue/job creation or automatic printing. Root cause remains unproven.
- Add regression checks for anchors, redaction, operation/format/compression labels, partial metadata, status/error paths and unchanged original calls; document one-print manual HAOS validation.

## 0.1.19

- Persist PAPPL app/queue and retrofit installable-option state in `/data/state`; retain generated HP PPD/runtime assets and ephemeral spool/capture paths under `/work`.
- Prepare only the persistent state directory before the existing privilege drop; migrate recognized legacy configuration after drop with bounded reads, no symlink following, atomic no-overwrite publication and no source deletion. Existing persistent state wins; failures stop startup safely.
- Add six bounded discovery-only startup attempts around the existing USB backend/retrofit enumeration, eight seconds per probe and 2/4/8/16/16-second backoff (142-second budget). Ready exits early; exhaustion remains observable and permits server/capture startup.
- Keep the confirmed working physical print path, PAPPL 1.3.1/pins, capture,usb allowlist, security identity/no_new_privs, token scrubbing, mDNS and IPP-only/no-TLS unchanged. No automatic queues or print jobs, device resets or permission changes to USB nodes.
- Add persistence/replacement/migration safety and retry state-machine regressions; update static checks, metadata, upgrade/acceptance documentation and standalone persistent mount instructions. Live HAOS/hardware acceptance remains manual.

## 0.1.18

- Add fail-closed INFO lifecycle instrumentation to the existing Debian PAPPL rebuild: decoded print/create/send operations, creation results, receipt/spooling bytes, registration/hold states, submission-time scheduler snapshots, thread launch results, execution modes and first device-open/final availability results.
- Add earliest safe retrofit callback entry markers before existing binding/backend diagnostics, plus a fixed startup marker.
- Log only numeric values and fixed enums; avoid named queue/client prefixes and bound repeated device waits/open attempts to first-attempt and final summaries.
- Preserve source selections, compatibility gate, transports, queue persistence and filter/backend behavior; add no retries, deadlines, state changes or automatic printing.
- Add reviewed source-excerpt fixtures and regressions for marker presence/order, redaction and fail-closed patching. Document coverage, asynchronous ordering and intentionally omitted stages in DOCS.
- Bump Dockerfile/config release metadata to 0.1.18. ARM64 build and live host/hardware acceptance remain independent review steps.

## 0.1.17

- Add a build-time PAPPL1 compatibility compile/link gate; validation-only, with no runtime behavior change.
- Add fixed-label queue binding and USB child launch diagnostics, including argument count and normalized DEVICE_URI validity.
- Reject invalid USB job invocation with a bounded error; retain discovery, transport, filters and 180-second deadlines without retries.
- Remove full discovered device URIs from startup diagnostics; add binding, launch and redaction regressions.

## 0.1.16

- Add guarded job-path instrumentation for spooled/streaming formats, each filter, chain and backend close results, first handoff bytes, totals and errno.
- Supervise HP filter/USB invocations with 180-second deadlines, sanitized bounded stderr, numeric exit/libusb codes, cancellation and no added retries; preserve binary streams and CUPS channels/state labels.
- Diagnostics-only: the remaining physical stall needs HAOS hardware evidence; no speculative conversion/USB fix.
- Preserve 0.1.15 mDNS/IPP-only, USB/security/capture and manual queues. No automatic queues or jobs.
- Add redaction, timeout, token, stream/channel and patch-guard tests; document exact HAOS acceptance and queue preservation.

## 0.1.15

- Enforce plain IPP on 8631 with `server-options=no-tls`; omit IPPS URIs/services and advertise security `none`.
- Rebuild the matching Debian PAPPL package with guarded TLS TXT keys for Avahi and mDNSResponder.
- Add bounded sanitized discovery diagnostics; flag unexpected local IPPS/TLS before reporting registration success.
- Preserve 0.1.14 Avahi runtime fixes, manual queues/state, USB/capture, HP filters, supplementary GIDs, no_new_privs, token scrubbing and Protection mode. No automatic queues or jobs.

## 0.1.14

- Fix Avahi runtime ownership validation by aligning its private account with UID/GID 10001; prepare only its runtime directory before privilege drop for HAOS `/run` tmpfs.
- Keep explicit hostname independent of machine ID, private D-Bus, host networking and protection mode compatibility.
- Add bounded sanitized Avahi failure reasons and require live private daemons before reporting resolved AirPrint registration success.
- Preserve manual queues, USB groups, capture/USB backends and HP filters; no automatic queues or print jobs.
- Add hostname, account ownership, fresh runtime, failure isolation and diagnostic regressions.

## 0.1.13

- Add private unprivileged D-Bus/Avahi for PAPPL AirPrint registration.
- Use HAOS host networking for LAN multicast; retain TCP 8631 and existing USB access.
- Add bounded service diagnostics and daemon supervision without automatic jobs or queue changes.
- Document manual queue preservation, USB regression gate and iPhone validation.
