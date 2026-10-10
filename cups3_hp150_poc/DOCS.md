# Experimental non-USB PoC

Install only on aarch64. Supply legally obtained AArch64 driver files in this
app's configuration directory before starting: `HP_Color_Laser_15x_Series.ppd`,
`rastertospl`, `libscmssc.so` and `cms/15xsc.cts`. This directory is mounted
read-only at `/hp-driver`; files must be readable by UID 10001.

The direct PAPPL HTTP/IPP service uses TCP 8631. There is no ingress. Use only
the `cups:capture:/hp150` queue: the app has no USB access and cannot print to
the connected printer. The TCP watchdog checks reachability only. Startup is
manual. `/work` is container-local experimental state; export captures before
rebuilds or removal. Keep backups containing your supplied driver files private.

The working `Deluka-BE/haos-cups-hp150` CUPS 2.4 release is separate and untouched.
See the [repository README](https://github.com/Deluka-BE/haos-cups3-hp150-poc#readme)
for installation, staging, capture testing and current validation limits.
