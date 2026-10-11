# Build with --platform linux/arm64; native ARM64 recommended for the ULD runtime.
FROM debian:trixie-slim
ARG LIBPPD_COMMIT=62666f01b167bdf5975b08fbab5c2f34d9277db3
ARG RETROFIT_COMMIT=49ad525a3715a57aae24c715ef0767b55ffb1991
ARG BUILD_VERSION=0.1.13
ARG BUILD_ARCH=aarch64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"
ENV DEBIAN_FRONTEND=noninteractive
RUN test "$BUILD_ARCH" = aarch64 && test "$(dpkg --print-architecture)" = arm64
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential autoconf automake libtool pkg-config gettext autopoint \
    libpappl-dev libcupsfilters2-dev libcups2-dev libcupsimage2-dev zlib1g-dev \
    avahi-daemon avahi-utils dbus dbus-bin ghostscript poppler-utils mupdf-tools fonts-dejavu-core python3 file binutils curl cups-ipp-utils usbutils libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
# Extract the real CUPS USB transport, without installing/starting a scheduler.
RUN mkdir -p /tmp/cups-usb /opt/poc/backend /opt/poc/diagnostics \
    && cd /tmp/cups-usb && apt-get update && apt-get download cups \
    && dpkg-deb -x cups_*.deb extracted \
    && cp extracted/usr/lib/cups/backend-available/usb /opt/poc/backend/usb \
    && chmod 755 /opt/poc/backend/usb \
    && ln -s /opt/poc/backend/usb /opt/poc/diagnostics/usb \
    && rm -rf /tmp/cups-usb /var/lib/apt/lists/*
WORKDIR /tmp/libppd
RUN git init && git remote add origin https://github.com/OpenPrinting/libppd.git \
    && git fetch --depth 1 origin "$LIBPPD_COMMIT" && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$LIBPPD_COMMIT" \
    && autoreconf -fi && ./configure --prefix=/usr --disable-static \
    && make -j2 && make install && ldconfig \
    && printf '%s\n' "$LIBPPD_COMMIT" > /usr/share/hp150-libppd-commit.txt
WORKDIR /tmp/retrofit
RUN git init && git remote add origin https://github.com/OpenPrinting/pappl-retrofit.git \
    && git fetch --depth 1 origin "$RETROFIT_COMMIT" && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$RETROFIT_COMMIT"
# Restrict the application itself, in addition to using a separate backend directory.
RUN python3 - <<'PY'
from pathlib import Path
p = Path('legacy/legacy-printer-app.c')
s = p.read_text()
old = '"", //"hp, gutenprint53+usb",'
assert s.count(old) == 1, 'Review upstream backend allowlist before building'
s = s.replace(old, '"capture,usb", // PoC: capture and real CUPS USB backend')
s = s.replace('PR_COPTIONS_QUERY_PS_DEFAULTS |', '/* PoC: disable device default queries */')
p.write_text(s)
PY
RUN autoreconf -fi && ./configure --prefix=/usr --disable-static \
    && make -j2 && make install && ldconfig \
    && dpkg-query -W > /usr/share/hp150-package-versions.txt \
    && printf '%s\n' "$RETROFIT_COMMIT" > /usr/share/hp150-retrofit-commit.txt
WORKDIR /opt/poc
COPY mdns/ /opt/poc/mdns/
COPY scripts/ /opt/poc/scripts/
COPY tests/ /opt/poc/tests/
RUN sh /opt/poc/scripts/stage-hp-uld.sh "$BUILD_ARCH"
RUN chmod 755 /opt/poc/scripts/* && mkdir -p /opt/poc/backend /work/state /work/spool /work/capture \
    && cp /opt/poc/scripts/capture.py /opt/poc/backend/capture \
    && cp /opt/poc/scripts/verify-capture.py /opt/poc/backend/verify-capture.py \
    && useradd --uid 10001 --no-create-home poc && mkdir -p /run/avahi-daemon /work/mdns && chown poc:poc /run/avahi-daemon && chown -R poc:poc /work \
    && rm -rf /tmp/retrofit /tmp/libppd
# Only the group/identity bootstrap runs as root; PAPPL, D-Bus and Avahi run after drop.
USER 0:0
ENV POC_PORT=8631
EXPOSE 8631
ENTRYPOINT ["python3", "/opt/poc/scripts/usb-runtime.py"]
