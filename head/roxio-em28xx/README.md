# The Roxio Video Capture USB on the Pi

A composite frame grabber for the bench: the console's video into
`/dev/video2` on the Pi, whole frames in correct colour, from a stick the
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

**A limit that was not one.** For an evening the driver seemed to
deliver 400 of 480 lines, and every register the built-in decoder's
setup writes was tried in turn to no effect. The cause was the driver's
answer to `VIDIOC_QUERYSTD`: the built-in decoder cannot detect a
standard, so the stock code answered "all of them", and v4l2-ctl feeds
that answer straight back into `S_STD` before it streams. A mask with
the 625-line bit in it made the driver program 576-line geometry with a
480/576 vertical scaler, and each 240-line field arrived as 200. ffmpeg
never asks, so it always got whole frames, which is how the difference
showed. The patch now answers the query with the standard in force
(`V4L2_STD_UNKNOWN` until one is set), and both tools stream 480 lines.
Two traps for whoever picks this up: `em28xx-v4l` is auto-loaded when
`em28xx` loads, so a module parameter reaches it only when `em28xx-v4l`
is what you modprobe; and the isochronous path looks like a broken
decoder (78 lines of noise) when it is only bandwidth.

**Against the scope.** `tools/eyes.py` takes a scope record of the same
composite and the grabber's frames together, decodes the record with
the family's own decoder, and scores the two pictures on the console's
pixel grid. That is the grabber's calibration: a TV chip's opinion of
the signal beside the measurement.

The composite feed now goes to the grabber. When the scope needs the
video again, a T at the console's jack feeds both.
