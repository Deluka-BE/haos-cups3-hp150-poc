# Experimental non-USB PoC

Install only on aarch64. Version 0.1.4 downloads HP's official ULD archive during
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

The direct PAPPL HTTP/IPP service listens on container TCP 863, published by
HAOS on host TCP 8631 (`863/tcp: 8631`). Open `http://<HAOS-IP>:8631/`.
Web UI and watchdog use `[PORT:863]` to resolve the configured host port.
After updating, check Configuration → Network maps `863/tcp` to `8631`.
The container entrypoint accepts only internal `POC_PORT=863`; host-side Docker
examples publish `8631:863`. There is no ingress.

The 0.1.3 listener on 863 disagreed with its old container-port mapping of 8631.
The pinned retrofit/PAPPL sources preserve 8631; no upstream truncation was
found. This release deliberately selects 863 without patching upstream. Why the
old deployed process selected 863 requires its actual arguments/image evidence;
see README for source references and remaining runtime verification.

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
