# Changelog

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
