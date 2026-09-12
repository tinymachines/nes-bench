# The Roxio Video Capture USB on the Pi

A composite frame grabber for the bench: the console's video into
`/dev/video2` on the Pi, a real picture in correct colour, from a stick the
internet had written off. Made 2026-09-11.

**What it is.** Roxio Video Capture USB (the Easy VHS to DVD stick), USB
id `1b80:e31d`, an Empia chip marked EM2980 that reports chip id 146.
No kernel knows that id: the stock em28xx says `unknown em28xx chip ID
(146)` and registers only its USB audio half. A 2014 linux-media thread
worked out that the 16 kB "Merlin" firmware means a CX25843-class
decoder is integrated, and stopped there.

**What changed since.** In 2026 mainline em28xx gained the EM2828X
family (chip id 148, the new Hauppauge USB Live2) with a built-in
decoder driven through the bridge's own registers, and the EM28281
(StarTech SVID2USB232) on the same path. The EM2980 is that family one
number over. So: mainline em28xx, built out of tree against the Pi's
6.12 kernel, plus this directory's patch.

**The patch** (`roxio-em2980.patch`, against the pinned mainline commit
in `build.sh`):

- two shims so 7.x source builds on 6.12: the `device-id/usb.h` include
  and the `kzalloc_obj` helpers;
- `CHIP_ID_EM2980 = 146`, named like its siblings;
- board 114, "Roxio Video Capture USB", decoder `EM28XX_BUILTIN`,
  composite and S-Video inputs, the USB id;
- bulk transfer by default for this board. Its isochronous endpoint
  delivers only the top sixth of each frame at every alternate setting
  (78 of 480 lines, measured); bulk delivers whole fields.

`build.sh` fetches the pinned sources, applies the patch, builds,
installs under `updates/` and loads. The module taints the kernel, as
out-of-tree modules do. The driver is GPL-2.0, like the kernel it came
from; the patch is a derivative and carries the same licence, separate
from this repository's MIT code.

**Capturing.** Select the input and standard once, then grab:

```
v4l2-ctl -d /dev/video2 --set-input=0 --set-standard=ntsc
ffmpeg -f v4l2 -standard NTSC -video_size 720x480 -i /dev/video2 -frames:v 8 -update 1 frame.jpg
```

Input 0 is composite, 1 is S-Video. The first frames after a start are
settling; skip a few.

**The limit, measured.** The decoder hands the bridge 200 active lines
per field, so 400 of a 480-line frame carry picture and the bottom
eighty rows stay whatever was in the buffer. Against the console's own
picture on a TV, the window starts about twenty console lines late and
stops about twenty early: a title screen with black borders looks
complete, a game loses its status line and its ground. Everything that
could be ruled out was, each by measurement:

- not the bridge's capture window register (forced to 144, 160 and
  200: no change);
- not any register group in the EM2828X standard or input-mux setup
  (each skipped in turn, and the PAL values tried under NTSC: no change);
- not the VBI mode, not the transfer buffer size or count (an 8-bit
  format still gives 399 lines, so the count is lines, not bytes);
- not the console's non-interlaced signal (the S-Video input with
  nothing connected also gives 401).

What would settle it is the vertical-window register of the EM2980's
decoder core, which the Windows driver knows and this driver does not.
Two traps met on the way, for whoever picks it up: `em28xx-v4l` is
auto-loaded when `em28xx` loads, so a module parameter reaches it only
when `em28xx-v4l` is what you modprobe; and the isochronous path looks
like a broken decoder (78 lines of noise) when it is only bandwidth.

The composite feed now goes to the grabber. When the scope needs the
video again, a T at the console's jack feeds both.
