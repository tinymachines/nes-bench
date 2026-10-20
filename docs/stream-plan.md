# NTSC to stream: the learning process, live

Proposed 2026-10-20, the evening the first game cleared. The plan log
(`docs/plan-log.md`) records the planner learning Super Mario Bros. a
level at a time; the retrospective (`docs/plan-retro.md`) reads it
back. Both are after the fact. This proposes showing the next game
being learned as it happens: the model searching, the part playing
what the search found, on a live stream. Two outputs, tried in this
order: YouTube, because the tool for it exists and only a key stands
in the way; then a streamer of our own, where the picture is not
video at all.

## What exists

| Piece | Where | State |
|---|---|---|
| The model as a media stream | `nes-shell/examples/stream.rs` (nes 8adf195) | Built, measured, committed, not pushed. A bench script on the model, NTSC encode, GPU decode with the CRT stage at 768x720, ffmpeg to H.264 (NVENC) and AAC at the console's exact rate, 1280x720 at 60 fps, to a file or to YouTube's RTMP ingest. Real time on a quiet box (console 11.3 ms a frame); 2 to 7% short at load 10. |
| The YouTube key | `6502/.env`, gitignored, mode 600 | Read as `YOUTUBE_STREAM_KEY`, never printed, cut out of ffmpeg's messages. First live test 2026-10-19: the handshake passed and the publish was refused. The owner's Studio side decides it (live enabled, current key). |
| The part's picture | Roxio Video Capture USB on the Pi, em28xx out of tree, now `/dev/video4` | Whole NTSC frames at 720x480, correct colour, proven against the scope (`docs/eyes-vs-scope.md`). The Pi's ffmpeg has `h264_v4l2m2m`, the hardware encoder. |
| The planner | `tools/plan.py`, `tools/plan-climb.py` | Logs per segment: positions kept, moves tried, deaths, backtracks. Saves states; the branch tool's `SHOT` gives any state's newest frame. |
| The head | `head/` on the Pi | Powers the console, streams the schedule, logs every poll; the grabber already takes frames at chosen latches. |
| The play page | tinymachines.ai `/nes/play` | `nes_wasm` and `ntsc_wasm` in the visitor's browser, WebGPU encode and decode, a worker per stage. The viewer's own machine is already a renderer. |
| Hosting | nginx on the workstation, static | No RTMP module. The `stream` module is for TCP, not media. Static files and a reverse proxy are what it does. |

Nothing above needs to be invented. What is missing is the joining:
a composition that reads as a learning process, a director that
turns planner events into picture, and the two outputs.

## What the viewer sees

One 1280x720 picture, three regions, held to the same clock.

- **The model, left.** The planner's current head: the kept position
  at the end of the last segment, played forward as a picture with
  the sound model's audio. When a segment is being searched, the
  candidates play in turn and the ones that die end on their last
  frame, dimmed. When a segment is kept, the head advances. This is
  the learning: the viewer watches moves tried, deaths, and the
  backtrack when every move dies.
- **The part, right.** The real console, from the grabber, playing
  the cleared schedule through the head. It lags the model by a
  level: the part plays what was proven, the model searches what is
  next. When a level clears on the model, the part's run restarts
  from power-on with the new schedule, which is the gate the plan log
  already enforces.
- **The ledger, below.** Level, x, segment, positions kept of the
  beam, moves tried, deaths, backtracks, planner time, and the part's
  poll count against the script. Every number is one the planner or
  the head already writes.

The first subject is the second cartridge, not Mario. Mario's
learning is finished and in the log; a rehearsal can replay it from
the log at speed, which is also the test of the director without a
planner running. The second game needs its own watch list and judge
(the retrospective's first next step), and that measuring is itself
worth showing.

## Output one: YouTube

The shortest path, because `stream.rs` already speaks RTMP.

1. **Clear the key.** The owner checks Studio: live streaming
   enabled on the channel, the key current, the event's visibility
   set to private or unlisted for tests. Visibility is set in Studio,
   not by the stream, so the stream never goes public by accident;
   going public is the owner's word each time.
2. **Re-run the 2026-10-19 test.** `stream.rs` with `youtube`, the
   test cartridge, 120 s. Pass: Studio shows the picture, the lag
   stays under a second, exit 0. A refused key stops the run with
   ffmpeg's reason, exit 1, as it does now.
3. **Composition.** `stream.rs` grows a second input and a ledger:
   the grabber's picture arrives from the Pi over the LAN (the Pi
   encodes with `h264_v4l2m2m` and sends MPEG-TS over UDP, or raw
   over TCP, measured for which holds 60 fps), the ledger is text
   rendered into the frame from the director's events. ffmpeg's
   filter graph composes; the model's picture is the clock.
4. **The director.** A small process reading the planner's log as it
   is written (the planner should stamp its own log, which the
   retrospective asks for anyway) and the head's bridge log, and
   feeding `stream.rs`: which saved state to play, which candidates
   to show dying, what the ledger says. First version: the planner's
   kept path, replayed as it grows, the deaths as a strip of last
   frames. Rehearsed on Mario's log before the second game starts.
5. **A session.** The second cartridge, from its watch list to its
   first cleared level, on a private stream, recorded. The recording
   is the measurement: does it read as learning to someone who was
   not there.

Load is the known risk. The planner and the stream share the
workstation and the planner is what loads it. Measured so far: the
chain is 2 to 7% short of real time at load 10. Two answers, tried in
order: NVENC and the GPU decode already take the picture off the
cores, so pin the planner to fewer cores and measure; failing that,
the model lane plays from saved states at a pace the chain sets, and
the ledger says so.

## Output two: our own streamer

Two forms. The first is ordinary and quick; the second is the one
that is ours.

**Low-latency HLS, served static.** ffmpeg writes fragmented MP4
segments and a playlist into a directory; nginx serves it under
tinymachines.ai; a page plays it with hls.js. No new process on the
box, no RTMP, cache headers set so the playlist is never stale. Three
to six seconds behind, which is fine for watching a search. This is
the fallback for every viewer and the thing to build the page around.

**The schedule stream.** The play page already runs the model in the
viewer's browser, exact at the poll. So the stream need not carry
pixels. It carries what the planner and the head produce: the button
bytes per poll, the segment boundaries, the branch events (a saved
state's identity, the moves tried, which died), and the ledger. The
viewer's browser runs the same model on the same ROM from power-on
and draws its own picture, bit for bit the planner's, with the
picture chain it already has. Bandwidth is bytes per poll, not
megabits; latency is the event's; the picture is exact rather than
encoded. The part's lane stays video (it is a camera, there is no
other way), carried as the HLS stream beside.

Three things decide its shape:

- **The ROM is the viewer's.** The site serves no commercial
  cartridge and never will. The page takes a dump from the viewer's
  own disk, checks its CRC against what the stream names, and refuses
  anything else. The family's own cartridges, served already, work
  without that step; so does any game the site is allowed to carry.
- **Catching up is a replay.** A viewer arriving mid-stream runs the
  schedule from power-on at speed to the live point. The model does a
  frame in milliseconds in the browser, so a level is seconds. A
  saved state at each level's intro, proven equal to the straight run
  (the retrospective's replay checkpoint), would make it instant and
  is the same work.
- **The transport is plain.** Server-sent events over nginx, one
  text line per event, the same line the director feeds the YouTube
  composition. One director, two outputs.

## Order

1. The key cleared and the 2026-10-19 test re-run (output one, step
   2). Blocked on the owner; nothing else is.
2. The director, rehearsed on Mario's plan log (output one, step 4).
   Measured: the rehearsal's events against the log's numbers, every
   segment accounted for.
3. The grabber lane from the Pi over the LAN, measured for frame
   rate and lag against the latch (the scope is the clock, as in
   `docs/eyes-vs-scope.md`).
4. The composition, to a file first, then YouTube private.
5. HLS served static and a page, from the same ffmpeg run.
6. The schedule stream on the play page: the family's cartridge
   first, then a viewer's own dump.
7. The second cartridge's watch list, on the stream.

Each step has a measurement before the next starts, which is the
discipline that got the first game played. Steps 3 and 5 can run
beside 2 and 4; nothing waits on 6 or 7.

## Rules this stays inside

- The key is never printed, logged or committed; ffmpeg's messages
  pass through the filter that cuts it. `.env` stays gitignored, mode
  600. Going public is the owner's word, set in Studio.
- No commercial cartridge's bytes, trace or picture is committed or
  served by the site. A YouTube stream of the owner's own console
  playing the owner's own cartridge is the owner's to make; the
  site's own streamer carries only the family's cartridges and the
  viewer's own dump.
- The Pi's name and address never reach a commit. The LAN leg of the
  grabber lane is configured in `.env`.
- Bench work goes through the Pi; mains stays as it is.
- `stream.rs` is unpushed. It goes out with its first proven live
  run, on the owner's word, like everything else.

## Open questions for the owner

- Which cartridge is the second game. The library has twenty dumps;
  a platformer with a short level and a plain death (the watch list
  is the work) would stream best.
- Whether the first public stream is Mario's rehearsal from the log,
  with the part playing the proven schedule beside it, or waits for
  the second game. The rehearsal is honest if the ledger says it is a
  replay.
- A name for the stream's page on the site, once there is one.
