#!/bin/sh
# Build-time staging only; never run HP's installer or binaries.
set -eu
[ "${1:-}" = aarch64 ] || { echo 'HP ULD staging requires BUILD_ARCH=aarch64' >&2; exit 1; }
[ "$(dpkg --print-architecture)" = arm64 ] || { echo 'HP ULD staging requires an ARM64 image' >&2; exit 1; }
archive_url=https://ftp.hp.com/pub/softlib/software13/printers/MFP170/uld-hp_V1.00.39.12_00.15.tar.gz
archive_sha256=cebb9b7b6125e7406634bb9c2a98b01477d1e11d66c7c90474669de9927bc91d
stage_tmp=$(mktemp -d)
trap 'rm -rf "$stage_tmp"' EXIT HUP INT TERM
curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' \
    "$archive_url" -o "$stage_tmp/uld.tar.gz"
printf '%s  %s\n' "$archive_sha256" "$stage_tmp/uld.tar.gz" | sha256sum -c -
tar -xzf "$stage_tmp/uld.tar.gz" -C "$stage_tmp" \
    uld/noarch/share/ppd/HP_Color_Laser_15x_Series.ppd \
    uld/aarch64/rastertospl uld/aarch64/libscmssc.so \
    uld/noarch/share/ppd/cms/15xsc.cts uld/noarch/license/eula.txt
install -d -m 755 /hp-driver/cms /usr/share/doc/hp150-uld
install -m 644 "$stage_tmp/uld/noarch/share/ppd/HP_Color_Laser_15x_Series.ppd" /hp-driver/
install -m 755 "$stage_tmp/uld/aarch64/rastertospl" /hp-driver/
install -m 644 "$stage_tmp/uld/aarch64/libscmssc.so" /hp-driver/
install -m 644 "$stage_tmp/uld/noarch/share/ppd/cms/15xsc.cts" /hp-driver/cms/
install -m 644 "$stage_tmp/uld/noarch/license/eula.txt" /usr/share/doc/hp150-uld/
python3 /opt/poc/scripts/validate-driver.py /hp-driver
