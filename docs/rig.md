# The QA rig: the cameras and the boards, in inches and pixels

The bench's eyes are fixed to a metal frame over a backing board, and
this file is what "fixed" means: where each thing is, so a moved camera
or board is a number to check against rather than a map to re-read.
Dimensions from the user, 2026-09-15; pixel scales MEASURED off the
frames named. `tools/board-overlay.py --read` reads the hole map off a
frame at a known pose; `docs/board-map.json` names the pose it was read
at.

## The backing board and the breadboards

| item | size | where |
|---|---|---|
| backing board | 12 by 18 in | under everything; the frame's uprights at its long edges |
| breadboard block | 6.5 by 10 in (three boards and a rail strip, side by side) | flush against the backing board's right short edge, centred, 3 in of board above and below it |
| the chip board | one of the three | the one nearest the backing board's edge (position as photographed: read off the frame, `docs/board-map.json` `band`) |

The breadboard's hole pitch is 0.1 in, which is what every pixel scale
below is measured against.

## The cameras

| camera | device (by-id) | job | mount | frame | scale |
|---|---|---|---|---|---|
| Logitech BRIO | `usb-046d_Logitech_BRIO_1C8D6975` | the board eye: the hole map, the named close-ups, the timed board grabs | on the frame's cross-bar over the breadboards, straight down, raised and levelled 2026-09-15, gaffer-taped and velcroed | 1920 by 1080, MJPG (USB 2: 4K is not on offer) | LOCKED 2026-09-15 (`captures/b15-all.jpg`): 11.1 px per hole at zoom 100, the same along columns and rows (level: no foreshortening), 28 at zoom 250, 53 at zoom 500; focus 18; the whole backing board in frame. The map is read per board off a zoom-250 frame (`docs/board-map.json` names each board's frame, aim and band) and the as-built photograph is drawn on those frames |
| Logitech QuickCam Pro 9000 | `usb-046d_0990_08DF0A45` | the side eye across the board: the three chips and the UNO's leads in profile from the Pi's side | on the backing board's Pi side, low, looking across the breadboards toward the console | 1600 by 1200, MJPG | LOCKED 2026-09-15 (`docs/lab/rig-side-eye-9000.jpg`): the chips at about a third of the frame's width; a housing's pins show in profile at about 4 px each |
| Logitech QuickCam Communicate Deluxe | `usb-046d_09a2_ABAD8310` | the second side eye, along the chip board's rails side from the cable end: the probe clips, the console cable's housing, U3's rails-side landings | on the frame's upright at the cable end, low | 1280 by 960, MJPG | LOCKED 2026-09-15 (`docs/lab/rig-side-eye-communicate.jpg`): column numbers legible to about column 25, the Q lines' arc and the housings in profile |
| Roxio capture (em28xx) | `usb-1b80_Roxio_Video_Capture_USB_...` | the console's picture | on the splitter with the scope's CH3 | 720 by 480 NTSC | not a camera |

## The bench, photographed

Four phone photographs of the whole rig, 2026-09-15, after the lock
(phone metadata stripped; the TV's picture blurred, since the site
carries no commercial game screenshots):

![the bench from the front: the console and its TV at the left, the frame over the backing board, the scope behind it](lab/rig-bench-front.jpg)

![the frame: the bench light on its cross-bar, the BRIO under it at the middle, the side eyes on the lower rail](lab/rig-bench-frame.jpg)

![the console's side: the mainboard with the cartridge in, the modulator, the probe clips, the breadboards beyond](lab/rig-bench-console-side.jpg)

![the bird's eye: the whole backing board as the BRIO sees it, the UNO and the Pi at the bottom, the QuickCam 9000 at the right](lab/rig-bench-birds-eye.jpg)

## The pose, locked

All three cameras and the boards were gaffer-taped and velcroed on 2026-09-15 night, the BRIO levelled (the tilt of the first raised pose, 9.2 px a hole along the rows against 11.1 along the columns, is gone: both read 11.1). Every named close-up lands on its target and the map's rings sit on the holes across both boards to column 56 (`captures/views-20260915T152127`). This is the baseline: a moved thing shows as a frame that differs from `captures/b15-all.jpg` by more than sensor noise (the timed grabs' worst 40 px block against it), and the fix is `--read` again, not a new tool.

## What a pose costs and buys

At the earlier height the BRIO's close-ups put 120 px on a hole and a
wire end reads beside its column number without effort; at the raised
height they put 53 px on a hole, half that, and the column numbers are
still legible. What the raised pose buys is the whole rig in one
frame: the UNO, the Pi, the console's mainboard and the modulator,
which is what the timed grabs want as a record. What it costs is the
fine read of a housing across two columns, which the side eye is for.

## When something moves

1. `python3 tools/eye.py sweep NAME --pi HOST --from 10 --to 40 --step 4`: the focus.
2. `python3 tools/eye.py grab bN-all --pi HOST --preset board`: the frame.
3. `python3 tools/board-overlay.py --read captures/bN-all.jpg`: the map and the views, if the pose is the rig's (straight down, `frame_rotate` set and the boards in their `band`s); otherwise the bands first.
4. `python3 tools/eye.py views --pi HOST` and `tools/view-rings.py` on the set: are the rings on the holes.
5. `python3 tools/board-overlay.py captures/bN-all.jpg`: the as-built photograph.
