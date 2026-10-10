# Experimental non-USB PoC

Install only on aarch64. Version 0.1.5 downloads HP's official ULD archive during
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
`:863`. Version 0.1.4 incorrectly treated that log as a mapping failure; this
update restores the known-good 0.1.3 ports and entrypoint validation semantics.
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

The working `Deluka-BE/haos-cups-hp150` CUPS 2.4 release is separate and untouched.
See the [repository README](https://github.com/Deluka-BE/haos-cups3-hp150-poc#readme)
for installation, staging, capture testing and current validation limits.
