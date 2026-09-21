# The probe plan: what to clip where, and what each position answers

Written 2026-09-21, when the offer was made to move the probes anywhere
on the bench, the NES's own chips included. This is the order to do it
in and the reason for the order, so that a session with the console open
spends its time on the measurements that close something.

Nothing here needs the SST39SF040 chips. Everything that does (the
calibration cartridge, the bars, hue against level) is in
`calibration-plan.md` and stays there.

## What the instrument allows

Measured, not assumed, and all of it already recorded elsewhere in these
docs:

- **Four channels, and the external trigger does not work.** The SCPI
  source `EXT` is refused on this DS1054Z (`wiring.md`, 2026-09-15), so
  a trigger costs a channel unless the measurement can trigger on one of
  its own signals. Most below can.
- **Memory is shared.** 24 M points on one channel, 12 M each on two,
  6 M each on four. The standing capture is 12 M on two channels at
  50 MSa/s, which is 240 ms, about 14 frames (`exercise.md`).
- **One capture to a run.** Reading 12 M points takes about 4000
  latches, so a second `TRIG` in the same run is always late.
- **CH2's lead broke on 2026-09-15** and the replacement is on the
  latch, unfitted. Three of the sessions below want CH2. Fit it first.
- **CH1 carries the trigger** on v1b whenever the run has to line up
  with a scripted latch. A session that self-triggers gets CH1 back.

The numbers every session below is measured against:

| quantity | value |
|---|---|
| master clock | 21.477272 MHz, 46.56 ns |
| master half-step | 23.28 ns |
| CPU cycle (M2 period) | 558.7 ns |
| PPU dot | 186.2 ns |
| frame | 16.6357 ms, 89342 dots (89341 on a short frame) |
| a short frame's deficit | one dot, 186.2 ns |

## Find the signals by their signature, not by a pin number

**This plan deliberately names no pin numbers.** There is no cartridge
pinout anywhere in this repository to check one against, and a pin
number carried in from memory is exactly the kind of claim this bench
exists to avoid. Every signal below identifies itself on the scope in
one sweep, which is both safer and a measurement in its own right:

- **M2** is the only 1.79 MHz square wave on the connector: 558.7 ns
  period, roughly half duty. Nothing else is near that frequency.
- **PPU A12** rests low for most of a line and rises in bursts tied to
  pattern fetches; with a background at $1000 it is high for most of the
  visible line and low across the blanking.
- **/IRQ** rests high and falls rarely. On a cartridge with no IRQ
  source it never falls at all, which is the control.
- **The master clock** is 21.477 MHz and lives on the chips, not the
  connector.
- **ALE** is on the 2C02 and runs at the dot rate's pattern.

Most of what follows is on the **cartridge edge connector**, which
means no soldering and no opening beyond the slot. Only M4 and M6 need
the chips themselves.

**Record the mapping once it is found.** The first session's real
output is a pinout written into `wiring.md` with "identified by
signature on <date>" beside each line, so no later session repeats this.

Ground the probes short. At 21 MHz a long ground lead rings, and the
master clock is the one measurement here that a sloppy ground will
quietly ruin rather than obviously break.

## M1. When rendering actually starts, from power-on

**Closes:** the open colour-phase item, which currently says "the part
was rendering by frame 7" as a **bound**, not a measurement. This turns
it into a number, and it may close the item outright.

The model turns rendering on at frame 11 and the part before frame 7
(`open-items.md`, and `nes-console`'s `origin-walk` for the model's
side). Two things are visible from power-on without touching a chip:

1. **When the picture stops being backdrop and starts being drawn.**
   That is rendering coming on, to the frame.
2. **Which frames were short.** A short frame is one dot less, 186.2 ns
   out of 16.6357 ms. Sync edge to sync edge is measurable to a few ns
   at these rates, so the part's own short/full sequence can be read
   directly rather than inferred from the origin.

The second is the one that would close it, because the origin difference
IS the count of short frames and nothing else.

- **Channels:** CH3 (video) **alone**, so the record gets all 24 M
  points.
- **Trigger:** on CH3 itself, the first sync edge after power. Single
  shot, armed before the head powers on.
- **Rate:** 50 MSa/s. 24 M points is 480 ms, about 29 frames, which
  brackets both frame 7 and frame 11 with room.
- **Record:** one capture from power-on, on the Duck Hunt path, with the
  same script as run `20260919-183919` up to its `TRIG`.
- **The answer:** a list of frame lengths. Short frames are 186.2 ns
  shorter than full ones. Count them up to the frame the model calls F
  and compare with `origin-walk`'s count for the same run.
- **What would make it lie:** scope timebase drift over 480 ms. Check by
  measuring a stretch of frames where the model says the parity is
  steady; those must come out alternating long/short cleanly. If they do
  not, the resolution is not there and this becomes a count of rendered
  frames only, which still bounds the item but does not close it.

## M2. The cartridge's /IRQ against the CPU's M2

**Closes:** `CART_IRQ_DELAY`, which is a **fit**, not a measurement.
`irq-sweep` says blargg's ROM allows 14 to 21 master half-steps and 17
is the middle. Seventeen half-steps is 396 ns, more than half a CPU
cycle, which is far too long for a wire: most of it probably belongs to
where inside its cycle the core samples IRQ, and this says which.

- **Needs an MMC3 cartridge in the console** (the multicart is mapper 66
  and has no IRQ source). Two of the twenty dumps are MMC3.
- **Channels:** CH1 M2, CH2 /IRQ. Two channels, so 500 MSa/s and 12 M
  each, 24 ms.
- **Trigger:** CH2 falling. Self-triggering, so no trigger channel is
  needed and the scripted latch is not involved.
- **The answer:** the time from /IRQ's fall to the next M2 edge, in ns,
  over many interrupts. Divide by 23.28 ns for master half-steps and
  compare with the band 14..21.
- **The control that makes it honest:** the same capture on a cartridge
  with no IRQ source must show /IRQ never falling. If it falls there,
  the probe is on the wrong line.

## M3. PPU A12 against M2's falling edges

**Closes:** the A12 filter item. The console counts ten **dots** of A12
low where the part counts three **falling edges of M2**, and a dot count
cannot hold a phase. Ten dots is what agrees with every ROM here, but
the argument behind it is about where the window starts against the
CPU's clock, and no ROM on this bench can see it.

- **Channels:** CH1 M2, CH2 PPU A12. 500 MSa/s, 12 M, 24 ms, which is
  about a frame and a half.
- **Trigger:** CH2 rising, with a holdoff long enough to land on the
  long low rather than a pattern-fetch gap.
- **The answer:** for each A12 low window, its length in ns and the
  number of M2 falling edges inside it, **and the phase of the first
  fall after A12 goes low**. That last number is the one the model
  cannot express.
- **The window that decides it** is the pre-render line to line 0 with
  the background at $1000, where the gap is exactly nine dots; every
  other window in a frame is two dots or hundreds. A commercial MMC3
  game with a $1000 background is the cheapest way there.

## M4. The alignment, against the master clock

**Closes:** E4. `knobs.toml` carries `cpu_phase 4` and `ppu_phase 3`
"measured by v2a03-sim clk-phase, v2c02-sim clk-phase", which is the
dies' own power-on recipes, not this part. E4 was always meant to set it
from the console.

- **On the chips**, not the connector: the master clock is not on the
  cartridge edge.
- **Channels:** two at a time, to keep 500 MSa/s (23 samples per master
  cycle). First pass CH1 master clock, CH2 M2. Second pass CH1 master
  clock, CH2 ALE.
- **Trigger:** CH1 rising.
- **The answer:** how many master clocks fall between the master edge
  and M2's edge, and the same for ALE. Those two integers are
  `cpu_phase` and `ppu_phase` read off the part.
- **Why two passes and not four channels:** four channels drops the rate
  to 250 MSa/s, 11 samples per master cycle, and this is the one
  measurement where that margin matters.

## M5. The reset pulse, against the latch train

**Closes:** "a short reset pulse is under the instrument's floor". The
poll stream cannot resolve less than about half a second because the
bridge hands lines over in 100 ms batches, so the head holds reset for
0.5 s on no evidence that less would work.

- **Channels:** CH1 the controller latch line, CH2 /RES.
- **Trigger:** CH2 falling.
- **Rate:** slow. 50 ms a division; a 100 ms gap in the latch train is
  plain at that scale.
- **The answer:** the shortest hold that still interrupts the latch
  train, which is the head's hold time with evidence under it.

## M6. Vblank, and why the startup wait runs long

**Closes:** nothing on its own, but it is the instrument for the
question M1 raises. If the part renders at frame 7 and the model at 11,
the difference is in a startup wait, and the usual shape of such a wait
is polling PPUSTATUS for two vblanks.

- **Channels:** CH1 the 2C02's /INT, CH2 video.
- **Trigger:** CH2, the first sync after power, as M1.
- **The answer:** when the first /INT falls after power-on, and its
  spacing thereafter, against the video's own frames. If the part's
  first vblank arrives earlier than the model's, that is the four
  frames.

## M7. The DMC fetch colliding with sprite DMA

**Closes:** nothing fully; this is a scope standing in for a logic
analyser. The 2A03 rung's DMC address register is disturbed by a
collision and stays where it lands, which contradicts the part
(`nes-console.md` memory, 2026-09-06). Naming the contradiction needs
the address bus, which four channels cannot carry.

- **What is worth doing anyway:** CH1 M2, CH2 R/W, CH3 one low address
  line, through a DMC-heavy passage. It will not name the register but
  it will say whether the collision costs the cycles the model thinks.
- **Do this last**, and only if the session has time left.

## The order, and why

1. **The identification sweep**, and write the pinout into `wiring.md`.
   Everything else depends on it and it is done once.
2. **M1**, because it is the freshest thread, needs one channel and no
   cartridge change, and may close an item outright.
3. **M6**, same probes as M1 plus one, same power-on run.
4. **M2 and M3** together: both want an MMC3 cartridge in the slot, so
   they share a cartridge change, and both are two-channel
   self-triggered.
5. **M4**, which is the only one that needs the chips and the only one
   where ground lead length decides whether the number is real.
6. **M5**, cheap and slow, good for the end of a session.
7. **M7** only if there is time.

## What to bring back

One run directory per measurement, as `b1-score.py` reads them: a
`.toml` naming the channels and the rate, the `.u8` per channel, the
script, and `knobs.toml`. The analysis for M1 does not exist yet and
will want writing against the record; M2 to M5 are edge timings that can
be read off the scope directly and written into the open item with the
capture beside them as evidence.
