#!/usr/bin/env bash
# The Roxio Video Capture USB (1b80:e31d, Empia EM2980) as a V4L2 capture
# device on the Pi: mainline em28xx, built out of tree against the running
# kernel, with this directory's patch. Run ON THE PI:
#
#   bash head/roxio-em28xx/build.sh            # fetch, patch, build, install, load
#   bash head/roxio-em28xx/build.sh --no-load  # stop after installing
#
# Needs: linux-headers for the running kernel, gcc, make, curl, patch.
# Installs into /lib/modules/$(uname -r)/updates/em28xx, where depmod
# prefers it to the stock em28xx, and the USB id then binds on plug-in.
# The kernel is tainted by the out-of-tree module. See README.md.
set -euo pipefail
MAINLINE=5225b8eec4c9bb21aecff6295fab6346a3c3738e     # torvalds/linux, the tree the patch is against
RPI=7d1826930811232688a50c99c540fbb137aed081          # raspberrypi/linux rpi-6.12.y, for the private headers
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$HOME/em28xx-roxio}"
K="/lib/modules/$(uname -r)"
[ -d "$K/build" ] || { echo "no kernel headers at $K/build (apt install linux-headers-rpi-v8)"; exit 1; }

echo "== 1. mainline em28xx at $MAINLINE"
mkdir -p "$WORK/inc/drx39xyj"; cd "$WORK"
for f in Kconfig em28xx.h em28xx-reg.h em28xx-v4l.h em28xx-cards.c em28xx-core.c em28xx-video.c \
         em28xx-i2c.c em28xx-input.c em28xx-dvb.c em28xx-audio.c em28xx-camera.c em28xx-vbi.c; do
  curl -sfL "https://raw.githubusercontent.com/torvalds/linux/$MAINLINE/drivers/media/usb/em28xx/$f" -o "$f"
done
echo "== 2. the tuner and demodulator headers the driver includes, from the Pi's own 6.12 tree"
for h in a8293.h cxd2820r.h drxd.h drxk.h lgdt3305.h lgdt3306a.h lgdt330x.h m88ds3103.h mb86a20s.h \
         mt2060.h mt352.h mt352_priv.h mxl692.h qm1d1c0042.h qt1010.h s5h1409.h s921.h si2157.h si2168.h \
         tc90522.h tda1002x.h tda10071.h tda18212.h tda18271c2dd.h tda18271.h ts2020.h tuner-simple.h \
         xc2028.h xc5000.h zl10353.h drx39xyj/drx39xxj.h; do
  ok=0
  for d in drivers/media/tuners drivers/media/dvb-frontends; do
    curl -sfL "https://raw.githubusercontent.com/raspberrypi/linux/$RPI/$d/$h" -o "inc/$h" && ok=1 && break
  done
  [ "$ok" = 1 ] || { echo "header $h not found"; exit 1; }
done
echo "== 3. the patch: two 6.12 shims, the EM2980 chip id, the Roxio board, bulk by default"
patch -p1 --forward < "$HERE/roxio-em2980.patch"
cp "$HERE/Makefile.oot" Makefile
echo "== 4. build"
make -s -C "$K/build" M="$PWD" modules
echo "== 5. install"
sudo mkdir -p "$K/updates/em28xx"
sudo cp em28xx.ko em28xx-v4l.ko em28xx-alsa.ko "$K/updates/em28xx/"
sudo depmod -a
[ "${1:-}" = "--no-load" ] && { echo "installed, not loaded"; exit 0; }
echo "== 6. load"
sudo rmmod em28xx_v4l em28xx_alsa em28xx 2>/dev/null || true
sudo modprobe em28xx-v4l
sleep 3
dmesg | grep -E "chip ID is|Identified as|analog set to|registered as video" | tail -4
v4l2-ctl --list-devices 2>/dev/null | grep -A2 -i roxio || echo "no Roxio device node: is it plugged in?"
