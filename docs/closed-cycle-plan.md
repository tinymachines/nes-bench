# Plan: the closed cycle

Written 2026-09-12, before the wiring that most of it needs. One run,
end to end: the cartridge in the console and the same bytes in the
model; power and reset under the script; the pad's bytes emitted by the
bridge or recorded from a hand; the console's picture and sound taken
three ways; the model run on the identical input history; and the
first frame where the two part, named. `bench-plan.md` states the
milestones B0 to B3 and their gates and nothing here changes them. This
page is how they join into a cycle now that the bench has a grabber, a
sound card, a camera and a way to dump the cartridge, and what is still
missing between here and the first full turn.

## The cycle, one turn

1. **The cartridge.** In the console, physically. Its bytes come off
   the reader as a dump (`card-plan.md`) and the model loads that file.
   "The same cartridge" is then a checkable fact, the CRC the reader's
   own database keys on, not a name on a label. A run records that
   CRC beside its script.
2. **Power and reset.** `POWER ON`, then `RESET`: the relay on GPIO27
   and the optocoupler on GPIO17, both from the head. The bridge's
   counters go to zero at the reset, so latch zero is the console's
   first poll after it.
3. **The pad.** Either the hand: `MODE PASS`, the original pad on the
   bridge's pad side, its bytes logged by latch index (B0); or the
   script: `MODE INJECT`, `SET` and `AT n hh`, the register holding the
   scripted byte at latch n (B1). The model is fed the same schedule
   through `set_pad` at the same polls. The pad's bytes are the only
   input the console has, and both sides see the same sequence.
4. **The capture.** Three eyes and an ear, each with its own time base:
   - the scope, armed by the script and fired by the bridge's trigger
     at latch `TRIG n`: one frame, as a waveform, at a latch index
     that is known exactly, decoded by ntsc-crt;
   - the grabber, the whole run as frames on the Pi, timestamped by
     the Pi's clock;
   - the sound card, the whole run as audio on the Pi, same clock;
   - the camera, a photograph on demand: the bench's state, not the
     picture.
5. **The model.** The same ROM, the same schedule, rendered to the
   frame at latch n (what `b1-score.py` already does through
   nes-console's `capture-score`) and, for the whole run, to a frame
   per poll.
6. **The comparison.** Decoder against model at latch n (B1's score);
   grabber against decoder (`eyes.py`, done); grabber against model
   (new, and the cheapest of the three to look at); sound against the
   model's stage (N7's item). Then replay and bisect (B3): the first
   latch at which a capture and the model disagree.

## Where each piece stands today

| piece | state |
|---|---|
| the head (`head/headd.py`): script words, relays, scope, runs served | built, run against fakes; not started on the Pi because the bridge's serial port is held by the bring-up bridge |
| the bridge firmware (`firmware/bridge-uno`) | on the UNO, answers `STATUS`; B0 sniff mode |
| the register, the pad on the bridge, the relays | not wired: sittings 3, 4 and 5 are the user's |
| the scope over SCPI | proven; `eyes.py pair` uses the same dialect |
| the grabber | `/dev/video2`, whole frames, driver in `head/roxio-em28xx/` |
| the sound card | ALSA card 3, records; nothing on its input yet |
| the camera | `/dev/video0`; not yet aimed at the board |
| the cartridge dump | reader flashed; the card plan is written, the reader on the Pi is not |
| the model at a latch | `capture-score` renders it; `b1-score.py` drives it |
| the comparison of pictures | `eyes.py compare`: decoder against grabber |

So today the cycle can capture but not emit: a hand plays, the scope
and the grabber watch. The emitting half is the wiring.

## What is missing, and the order it closes in

**C0, capture only, no wiring needed.** The model's title screen
against the console's, through both eyes. A title screen after reset
is the same picture on every frame, so it needs no latch alignment:
the dumped ROM into the model, one frame rendered, beside the
decoder's frame and the grabber's from `eyes.py pair`. Gate: the
three pictures on the console grid, the flat-block agreement between
each pair reported, and the first flat block where the model differs
from both eyes named. Needs the card plan's first pull. MUTATE: the
model fed a different ROM must fail the flat-block agreement.

**C0: DONE 2026-09-12.** The cartridge dumped and its checksum the
database's; the console given mapper 66 (nes-bus v0.1.2, ntsc-crt
v0.2.9, the chip repositories moved with them); the three pictures on
the console grid in `eyes-vs-scope.md`. The finding: the two eyes agree
to a degree of hue and the model sits twelve to fourteen degrees off
both on the saturated colours. The mutation stated above is not yet
run: the tool has no `--expect-fail` and it should, before C1.

**C1, the hand recorded with pictures.** Sittings 3 and 4 (the
register and the pad on the bridge), the head owning the UNO's port
(the bring-up bridge's unit stops when the head's starts;
`Conflicts=` between the two units says so), and three new head words:
`EYES ON` / `EYES OFF` (the grabber recording the run to a file in the
run's directory, with the Pi's clock), `EARS ON` / `EARS OFF` (the sound
card, the same), `PHOTO` (the camera, one frame, into the run). The
bridge's log already carries a wall-clock stamp per latch on the head,
so any grabber frame maps to a latch within one frame. Gate: B0's
gate as stated, plus a run directory that carries the log, the frames,
the audio, and one photograph, and a tool that plays the frames back
with the latch index and the byte overlaid, which is the movie a human
reads. MUTATE: the grabber's timestamps shifted by a second must move
the overlay off the visible poll.

**C2, the full turn.** Sitting 5 (the relays, the trigger), then one
script: `POWER ON`, `RESET`, `MODE INJECT`, an `AT` schedule, `ARM`,
`TRIG n`, `CAPTURE`, `EYES OFF`. The model on the same schedule. Gate:
B1's and B2's gates as stated; in addition, the grabber's frame at the
trigger identified by matching against the decoder's frame (frame
differencing around the trigger's wall-clock time), and its distance
in frames from the latch recorded per run, so the two eyes are tied to
the one time base that is exact. MUTATE: the schedule shifted by one
latch on the model only must fail the frame comparison, as B1 says.

**C3, replay and bisect with pictures.** B3 as stated, with the
grabber's movie beside the bisection: the first latch where the model
and the part disagree, and the frames either side of it as a person
sees them.

## Three things decided here

- **The head owns the port once the bridge is built.** Until sitting 4
  closes, the bring-up tool needs the UNO through the serial bridge
  unit; after it, the head does, and it carries a `bridge` word for the
  bring-up tool's occasional question. Two owners of one port is how
  the flashing trap in `head/README.md` happened.
- **The scope's trigger is the only exact clock.** The grabber and the
  sound card are continuous and timestamped; their frames are placed
  against the latch index by measurement (the trigger frame found in
  the grabber's stream), never by assuming a latency.
- **Nothing is compared to a name.** A run is (the ROM's CRC, the
  script, the captures); the model is run on the file with that CRC.
  A cartridge the database does not know is still a CRC.
