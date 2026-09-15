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
| Logitech BRIO | `usb-046d_Logitech_BRIO_1C8D6975` | the board eye: the hole map, the named close-ups, the timed board grabs | on the frame's cross-bar over the breadboards, straight down; raised 2026-09-15 so the whole backing board is in frame | 1920 by 1080, MJPG (USB 2: 4K is not on offer) | RAISED POSE 2026-09-15 (`captures/b14-all.jpg`, with the bench light): 11.1 px per hole along the columns and 9.2 along the rows at zoom 100 (the camera is tilted: it looks up the board toward the console, and the row pitch is foreshortened by 0.83 on the chip board and 0.91 on the middle board), 53 at zoom 500; focus 22. The map is read off a zoom-250 frame with `--read --zoomed` at this height, since 11 px on a hole is under what the hole finder resolves at zoom 100; a tilted camera makes that read fragile (the rows of one board are taken for another's), so the pose is not mapped until the camera is levelled. EARLIER POSE (`captures/b12-all.jpg`): 24 px per hole, focus 25, the breadboards filling the frame |
| Logitech QuickCam Pro 9000 | `usb-046d_0990_08DF0A45` | the side eye: a low view along the chip row, where a housing's pins are in plain view | on the backing board's Pi side, low, looking across the breadboards | 1600 by 1200, MJPG | the chips at about 300 px across the frame as aimed 2026-09-15: bring it closer and lower along the row |
| Logitech QuickCam Communicate Deluxe | `usb-046d_09a2_ABAD8310` | not aimed yet: the middle board and the pad housing, or the console's port | on the frame's upright | 1280 by 960, MJPG | as found 2026-09-15 it looks at the room |
| Roxio capture (em28xx) | `usb-1b80_Roxio_Video_Capture_USB_...` | the console's picture | on the splitter with the scope's CH3 | 720 by 480 NTSC | not a camera |

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
