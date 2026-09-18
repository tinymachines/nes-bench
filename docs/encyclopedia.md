# The encyclopedia of NES code patterns

What the x-rays add up to (`exercise.md`, Programme 3). An entry is a
pattern's name, what it does, its signature as the x-ray measures it
(the addresses it touches, the event kinds it raises, its cycle counts
on the die's rungs), a window to stand in on the 6502 site's Halfshot
page, the cartridges it was found in by CRC, and the mechanism it
teaches. An entry carries the shape of a pattern and never a commercial
cartridge's bytes: code appears only from ROMs whose source is ours.

Every number here was produced by `tools/xray.py` on the model, whose
CPU is held to the die by the recorded bus (`trace-plan.md`, T1); the
part confirms an x-ray by the action's effects, never by its fetches,
because the bench has no address bus.

## 1. The poll routine

**What it does.** Reads the controller: strobe the shift register (a 1
then a 0 to `$4016`), then read `$4016` eight times, each read one
button on D0, shifting the bits into a RAM byte.

**Found in.** The pad cartridge, `pad-paint.nes` (`nes-console`
`testrom::pad_paint_program`, crc32 of the paint variant as
`export-testrom` writes it), whose source is ours, so the code is
shown. The multicart's menu polls the same way (entry 2).

**The x-ray.** `tools/xray.py runs/pad-paint.nes pad-a --latch 6 --byte
01 --frames 12 --bytes --window`: A pressed for one latch at latch 6,
against not.

```
diverge h 531570: read of $4016 returned 0 in the base run and 1 with the byte (D0); latch 6 at h 531559, 11 half-cycles after it
  the instruction: LDA $4016 at $810E (its fetch at h 531564), reads read 6 half-cycles in
the path: 48 half-cycles differ in 11 span(s) over 290 half-cycles before the next latch, 11 instructions; then 1 span(s) after it
  h 531570..531571  LDA $4016 at $810E: pad $4016 read D0 1 (base 0)
  h 531585..531585  ROR $02 at $8112: RAM $0002 <- 80 (base 00)
  h 531612..531617  ROR $02 at $8112: RAM $0002 read 80 (base 00); RAM $0002 <- 80 (base 00); RAM $0002 <- 40 (base 00)
  ...  (six more rotations, the bit walking down to bit 0)
  h 531846..531847  LDA $02 at $8121: RAM $0002 read 01 (base 00)
  h 531859..531859  STA $2007 at $8125: PPU $2007 <- 01 (base 00)
  (echo) h 591136..591140  ROR $02 at $8112: RAM $0002 read 01 (base 00); RAM $0002 <- 01 (base 00)
rejoin: the records agree again from h 591141 to the end (714732)
signature: code at $810E..$8125, RAM touched $0002, 8 pad reads, 3 PPU writes, 0 cart writes on the path
```

**Signature.** Eight reads of `$4016` exactly 32 half-cycles apart (16
CPU cycles: `LDA abs` 4, `LSR` 2, `ROR zp` 5, `DEX` 2, `BNE` taken 3),
the strobe's two writes before them, one RAM byte written eight times
with the bit walking from bit 7 to bit 0, and the byte read once after.
The pad's byte enters the CPU 11 half-cycles after the latch and is a
whole byte in RAM 290 half-cycles later. The `ROR zp` is a
read-modify-write: the x-ray shows each one as a read, the old byte
written back, then the new byte, which is the 6502's double write on
the die and not a quirk of the tool.

**The code.** From `testrom.rs`, the NMI handler at `$8100`:

```
8100  INC $00          ; the frame count
8102  LDA #$01
8104  STA $4016        ; strobe up
8107  LDA #$00
8109  STA $4016        ; strobe down: the register holds the eight buttons
810C  LDX #$08
810E  LDA $4016        ; <- the x-ray's divergence: D0 is the button
8111  LSR A            ; D0 into the carry
8112  ROR $02          ; the carry into bit 7 of the byte, the rest down
8114  DEX
8115  BNE $810E
8117  ...              ; the paint: $2006 <- $3F, $01; $2007 <- $02 & $3F
```

**The window.** `pad-poll-6.window`, shipped on the Halfshot page
(`halfshot?window=pad-poll-6`, the same cartridge's poll at latch 6 from
the NMI entry), and the x-ray's own `pad-a.window` (312 half-cycles
from the load's fetch to the palette write, 13 overlay lines) to ship
beside it.

**The mechanism.** The controller is a shift register (a 4021) clocked
by reads: the strobe loads it, each read of `$4016` presents one bit and
the falling edge of the read clocks the next. A game owns the timing of
its own poll, which is why the port's latch width and clock spacing on
the bench are the game's cycle counts and not the console's
(`bench-v1b-uno.md`). The 16 cycles between reads here are this
routine's; a game with an unrolled loop reads faster, and the DMC's
fetch can clock the register twice (`pad-dmc`, the nine-clock polls
`pad-log` predicts).

**The dispatch.** This cartridge's action on the byte is the smallest
there is: the byte, masked, into palette entry 1, so the picture shows
what was read. That is entry 1's second half and the seed of entry 3
(the dispatch from the pad's byte to the action) once a game's is
x-rayed.

## 2. The bank switch: a menu's Start

**What it does.** A multicart's menu polls the pad, and on Start
turns rendering off, writes the game's bank into the mapper's register
and starts the game from its reset vector. The bytes are a commercial
cartridge's, so this entry is shape only: addresses, counts, event
kinds, and what the x-ray reported with every fetched byte masked.

**Found in.** Super Mario Bros. + Duck Hunt (USA), crc32 D26EFD78,
mapper 66 (GxROM: one register at `$8000..$FFFF`, bus-conflict AND).

**The x-ray.** `tools/xray.py <rom> smbdh-start --latch 200 --byte 08
--frames 222 --out <the ROM store>`: Start for one latch at latch 200,
the menu's 190th poll, against not. The report, as far as it stays
shape:

```
diverge h 12535332: read of $4016 returned 0 in the base run and 1 with the byte (D0); latch 200 at h 12535197, 135 half-cycles after it
  the instruction: AND $4016 at $8172 (its fetch at h 12535326), reads read 6 half-cycles in
the path: 27570 half-cycles differ in 2 span(s) over 27574 half-cycles before the next latch, 4592 instructions; then 7 span(s) after it
  h 12535332..12535333  AND $4016 at $8172: pad $4016 read D0 1 (base 0)
  h 12535338..12562905  INC $03 at $8177: a different code path from $8178: 11454 fetches differ; RAM: 32 writes to 19 addresses (most: $0003 x10, $01FF x3, $01FE x2, $0060 x2, ...); PPU: 2 writes ($2000 <- 90, $2003 <- 00); cart: 0 writes
  (echo) h 12595070..12595071  LDA $04 at $817C: RAM $0004 read 10 (base 00)
  (echo) h 12595113..12595113  STA $47 at $818A: RAM $0047 <- 10 (base 00)
  (echo) h 12595238..12595239  LDA $47 at $8089: RAM $0047 read 10 (base 00)
  (echo) h 12595248..12595249  AND $E0 at $808D: RAM $00E0 read D0 (base 00)
  (echo) h 12595254..13222545  LDA #$.. at $8091: a different code path from $8092: 277692 fetches differ; ...; PPU: 5606 writes ($2001 <- 00, ...); cart: 1 writes (cart $BF00 <- 00 (base 20))
rejoin: never; the action run is 3 half-cycles longer than the base run over the same frames
after the path, to the end of the record:
  ppu 12595265 $2001 <- 00 at frame 211 line 121
  cart 12595319 $bf00 <- 00 (a mapper register) at frame 211
  ppu 12755981 $2001 <- 06 at frame 214 line 42
  ppu 12758123 $2000 <- 10 at frame 214 line 52
  ...
  sprite DMAs ($4014) after the path: 6
signature: code at $8172..$8177, RAM touched $0000, $0003, $0004, $0005, $0022, $0047, $0050, $0051, $0060, $00E0, $01F7, $01F8 and 7 more, 5 pad reads, 3 PPU writes, 0 cart writes on the path
```

**Signature.** The poll is entry 1's shape with different numbers: eight
reads of `$4016` 38 half-cycles apart (19 cycles a bit; the pad
cartridge's is 16), the bit tested by an `AND` on the read rather than
rotated, and Start is the fourth bit, so the divergence lands on the
fourth read with five reads after it, spaced 46 half-cycles once the
branch on the bit is taken. The press is not acted on in its own frame:
the poll's frame writes 19 RAM addresses (a counter at `$0003` ten
times, the stack, `$0060`) and ends in the sprite DMA like every
other. At the next latch the byte comes back out of RAM (`$0004`,
`$0047`), the dispatch at `$8089` reads it, and the switch follows
within 60 half-cycles: rendering off (`$2001 <- 00` at frame 211 line
121), then the mapper register (`$BF00 <- 00`: both banks to zero, the
first game) 54 half-cycles later, then a code path that never rejoins
(the game's own reset), rendering back on at frame 214 line 42 (`$2001
<- 06`, then `$2000 <- 10`, the game's NMI on) and a frame loop that
toggles `$2000` between `90` and `10` around each frame's DMA.

**The window.** Not cut yet: rung 0 has to run the record to the
fetch, twelve million half-cycles, about seven minutes, and a window
inside a commercial cartridge's run carries its bytes, so it would stay
where the ROM store is and never be served.

**The mechanism.** GxROM's register is the whole ROM space, and the
board ANDs the written byte with the ROM byte under it (the bus
conflict), so a menu writes the bank through an address whose ROM byte
already holds the value: `$BF00` holds `00` in this cartridge's menu
bank, which is why the write lands there. Rendering goes off first so
the switch, which swaps the CHR bank too, does not tear the frame; the
game then starts from its own vector and its first act is to turn the
picture back on with its own `$2000` and `$2001`. The 3 half-cycles by
which the action run is longer are the odd-frame dot the PPU skips
with rendering on: the two runs' frames are no longer the same length
once one of them has rendering off for three frames.

**What the part can confirm.** Not the fetches (the bench has no
address bus) but the effects: the poll count, the picture at a trigger
after frame 214 (E2 did exactly this: the title at latch 300), and the
sound. What it cannot yet: the frame at which rendering went off, until
the scope is triggered at latch 201 and the decoded record shows the
blank frames. Asked (2026-09-18), the part switches on the same
press, cold or after any number of resets, the poll moving to the
title's lines as the model's does; an earlier reading that a
cold-booted part ignored it was the bench's head catching the menu
before the press (`open-items.md`).

## 3. The game loop inside the interrupt

**What it does.** The main program spins on one instruction; the whole
game runs in the NMI handler, which turns NMIs off at its entry and on
before its `RTI`, so a long frame is dropped and never re-entered.

**Found in.** Super Mario Bros. (`mario-dissection.md`): `JMP $8057`
at `$8057`, 5,800 spins a frame, 58 percent of it; the handler at
`$8082`, `$2000 <- 10` at line 241 dot 79, `$2000 <- 90` at line 89,
`RTI` at `$8181`.

**Signature.** An idle loop of one instruction that every frame's
profile finds at the same address; the vector taken at line 241; the
first PPU write of the handler clearing bit 7 of `$2000` and the last
setting it.

**Mechanism.** The NMI is the frame clock. With the game inside it, the
frame is the unit of everything, and the guard is what a frame overrun
costs: one dropped frame, not a corrupted one.

## 4. The sprite-0 split for a status bar

**What it does.** Waits for the sprite-0 hit flag at the bottom of a
fixed status bar, then writes the level's scroll, so the bar stays and
the world moves under it.

**Found in.** Super Mario Bros.: `$2002` read once at `$813D` (the flag
clear), `LDA $2002 / AND #.. / BEQ` at `$8150` spun 178 times from line
16 to line 30, a `DEY / BNE` delay of 19 at `$8159`, `$2005` twice at
line 31 dot 100, `$2000` at dot 157 (the PPU's own lines and dots
since 2026-09-18; `dissect.py` had them up to 0.7 line high).

**Signature.** A spin on `$2002` that ends at the same line every frame
(30 here, the bar being 32 lines), a short counted delay into the
blank, two `$2005` writes and one `$2000` at the next line.

**Mechanism.** The 2C02 sets bit 6 of `$2002` when sprite 0's opaque
pixel meets an opaque background pixel; a sprite parked at the bar's
bottom edge makes that a scanline timer. The delay walks the write to
the horizontal blank so the change lands between lines. What the
bench can test: a decoded capture must show the bar unscrolled above
line 32 and the level scrolled below.

## 5. The VRAM buffer drained in the blank

**What it does.** The game's logic, running during the picture, queues
nametable and palette writes in RAM; the handler writes them to `$2007`
in the blank, after the DMA, before rendering goes on.

**Found in.** Super Mario Bros.: the buffer at `$0300`, drained by
`STA $2007` at `$8EBB`; 4 bytes to `$3F0C` and 3 to `$207A` every four
to five frames, 26 to a nametable column (`$2490`) when the scroll
crosses sixteen pixels; the address parked at `$3F00` then `$0000`
after; rendering on at line 247, 249 or 252 by the burst's size.

**Signature.** No `$2007` write outside the blank; bursts right after
the DMA's 256 writes; four `$2006` writes closing every burst.

**Mechanism.** VRAM is writable only while the PPU is not fetching, so
the picture's work is deferred into a queue and the blank's budget
(about 20 lines here) is what bounds a frame's update: one column of
26 tiles is the biggest thing this game ever writes in a frame.

## 6. The jump engine

**What it does.** A routine called by `JSR` pulls its own return
address, indexes the table of addresses that follows the `JSR`, and
lands by `JMP` indirect: a switch on a byte with the cases written as
a table right after the call.

**Found in.** Super Mario Bros.: `$8E04`, entered 474 times in 100
frames; tables after the `JSR`s at `$8215` (the operation mode),
`$AEDF` (the game mode), `$B04C`, `$B34E` (the player's state), `$C88F`,
`$C907`, `$92C8`. Nine tables in 100 frames.

**Signature.** Two `PLA`s in a routine entered by `JSR` before any
`RTS`; a `JMP ($..)`; the callee's `RTS` returning to the address the
caller's caller pushed. The profiler closes the engine's frame at the
`JMP` and runs the routine it lands on as a call of its own.

**Mechanism.** The 6502 has no indexed jump; the trick makes the return
address a table pointer. One engine, and every mode, state and object
type in the game is a table.

## 7. The state dispatch

**What it does.** The player's state (on the ground, in the air, ...)
indexes a jump-engine table; a press changes the state and the next
frame runs a different routine.

**Found in.** Super Mario Bros.: the table after `$B34E`, `$B35A` for
54 of 100 running frames and `$B376` for 46 (the scripted jump); the
x-ray of a press on the ground: `$B376` is the one routine that ran
only in the pressed run, 746 half-cycles, after the test at `$B484`
(`AND $0D`: A now against A last frame) sent the physics down a
different path.

**Signature.** A routine present in one run's tree and absent from the
other's, reached from the engine, in the frame of the press.

**Mechanism.** A state machine written as a table. The x-ray's routine
diff finds the transition without reading the code: that is the
method entry 7 exists to record.
