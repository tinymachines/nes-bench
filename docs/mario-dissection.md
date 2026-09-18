# Super Mario Bros., dissected on the model

The first game taken apart with the x-ray and the frame profiler
(`exercise.md`, Programme 3): how it is laid out, how it runs its
loop, what it does on which scanline, and what happens between the pad
and a jump. Everything here was measured on the model's record of the
multicart (`tools/dissect.py`, `tools/xray.py` on `nes-console`'s
trace), whose CPU is held to the die by the recorded bus; nothing was
read out of a listing first and confirmed after. The cartridge's bytes
are ROM content and stay where the ROM store is, so this document
carries the game's shape (addresses, scanlines, counts, mnemonics with
their immediates masked) and never its code or its pictures.

## The record

One run, 660 frames from power-on, `play.txt`: Start at latch 200 (the
multicart's menu), Start at latch 330 (the game's title), Right from
latch 520, A from 570 to 590, Right released at 640. Its states, from
the pictures the trace writes: the title at frame 331, the black
transition at 500, Mario running with the screen scrolling by 585, a
question block passing at 640. 39.3 million CPU half-cycles, 645
latches, 189,434 PPU writes, 479 mapper writes, 1298 NMI edges, 1.1 GB
of pins, written in 6.7 s.

## The loop: the whole game runs inside the interrupt

The main program, once it has set the console up, is one instruction:
`JMP $8057` at `$8057`, a jump to itself. Every gameplay frame the
profiler finds it spinning there from the handler's return until the
next NMI, 5,800 times, 34,842 half-cycles, 58 percent of the frame. The
game is its NMI handler, entered at `$8082` through the vector at
line 241, ended by an `RTI` at `$8181` between lines 87 and 114 of the
next frame. Its first act is to turn NMIs off (`$2000 <- 10` at line
241 dot 149) and its last, before the `RTI`, to turn them back on
(`$2000 <- 90`), so a frame whose handler runs long is dropped rather
than re-entered.

The handler in scanline order, frame 600 (a plain running frame, no
column to load):

| line | dot | what | where |
|---|---|---|---|
| 1 | 226 | `$2002` read once: the sprite-0 flag seen clear | `$813D` |
| 16 | 60 | `LDA $2002 / AND #.. / BEQ` spun 178 times: waiting for sprite 0, to line 30 dot 92 | `$8150` |
| 30 | 122 | the hit; `DEY / BNE` 19 times, a delay to line 31 dot 66 | `$8159` |
| 31 | 100 | `$2005 <- 02, 00`: the level's scroll set below the status bar | |
| 31 | 157 | `$2000 <- 10`: the nametable for the level | |
| 31 to 89 | | the game's logic: the operation-mode tree | `$8212` from `$8175` |
| 89 | 26 | `$2002` read, `$2000 <- 90`: NMIs on | `$8178` |
| 89 | 58 | `RTI`, and the spin at `$8057` until line 241 dot 12 | `$8181` |
| 241 | 28 | NMI vector taken | `$8082` |
| 241 | 79 | `$2000 <- 10`: NMIs off, nametable 0 | |
| 241 | 163 | `$2001 <- 06`: rendering off for the blank's work | |
| 241 | 175 | `$2002` read: the status cleared | `$80A6` |
| 241 | 211 | `$2005 <- 00, 00`: the scroll zeroed for the status bar | |
| 241 | 253 | `$2003 <- 00`, then `$4014 <- 02`: sprite DMA from `$0200` | |
| 241 | 273 | the DMA's 256 writes of `$2004`, to line 246 dot 105 | |
| 246 | 189 | `$2002` read, the VRAM buffer drained (none this frame) | `$8EDD` |
| 246 | 228 | `$2005 <- 00, 00` | |
| 247 | 34 | `$2001 <- 1e`: rendering on | |
| 250 | 295 | the pad polled (the strobe's fall), 16 reads (both ports) | `STA $4016` at `$8E63` |

The table runs in the PPU's order: the frame begins with the pre-render
line and the picture, and ends with the blank, so the handler that
draws frame 585's picture ran at the end of frame 584. (Lines and dots
are the PPU's own since 2026-09-18: `dissect.py` had numbered the
pre-render line 0 and drifted a dot for every dot a rendered odd frame
skips, which put its lines up to 0.7 high; see "Done on the part".) So
the blank is spent on the DMA, the VRAM buffer and the sound and pad
routines; the top of the picture is spent waiting for the sprite-0 hit
at the bottom of the status bar (lines 16 to 30, the bar being 32 lines
tall); the scroll for the level is written at line 31, which is the
split; and the game's own logic runs during the visible frame from line
31 to about line 89. A frame that loads a column of the next screen
(frame 615: 26 bytes to `$2490`) puts rendering on at line 252 instead
of 247 and ends its handler at line 98; the logic's budget is what is
left of the picture.

Over frames 560 to 659: the NMI at line 241 every frame; rendering on
at 247 (249 with a 4-byte burst, 252 with a column); the `RTI` at 87
or 88 on plain frames, 108 to 114 when a column loads or the world
gets busy; the idle 58.4 percent on plain frames, 48 to 50 percent on
the busy ones. Nothing ever runs past line 241: the frame is dropped
by the NMI guard before it can.

## The routines

The game dispatches through one jump engine at `$8E04`, called by
`JSR` and entered 474 times in 100 frames: it pulls its own return
address, indexes the table that follows the `JSR`, and lands by `JMP`
indirect. The profiler follows it. The tree of a running frame, by
half-cycles inside each routine (per frame, from the 100-frame
profile):

| routine | from | per frame | what the table says |
|---|---|---|---|
| `$8212` | `$8175` in the handler | 14,777 hc | the operation-mode tree: `JSR $8E04` at `$8215`, table -> `$8231` (title), `$AEDC` (game) |
| `$AEDC` | the table | 14,659 | the game mode: `JSR $8E04` at `$AEDF` -> `$AEEA` (playing), `$8567` (the transition) |
| `$AEEA` | the table | 14,553 | the core of a frame: the player, then the objects |
| `$B04A` | `$AEF3` | 6,123 | the player: `JSR $8E04` at `$B04C` -> `$B0E9` |
| `$B0E9` | the table | 6,007 | player control: `JSR $8E04` at `$B34E` -> `$B35A` on the ground, `$B376` in the air |
| `$C047` | `$AF05`, six times a frame | 3,463 | per object: six enemy slots |
| `$DC64` | `$B15A` | 2,970 | |
| `$8223` | `$814A`, right after the split | 2,046 | |
| `$EEE9` | `$AF16` | 1,821 | |
| `$F180` | `$B14F`, `$AF10` | 1,432 | |
| `$8E5C` | `$80E7` in the blank | 1,084 | the pad, both ports |
| `$F2D0` | `$80E4` in the blank | 955 | the sound engine |
| `$8F97` | `$80ED` in the blank | 877 | |
| `$8EDD` | `$80C3` in the blank | 265 | the VRAM buffer drained |

The call tree reaches depth 7 (`$9BE1`, 760 calls in 100 frames from
`$E408`). The title frame runs the same handler with `$8215 -> $8231
-> $8245` and the same core below it (the demo is the game playing
itself); the transition frame runs `$8215 -> $AEDC -> $8567 -> $889D`
and its handler is over by line 1, the idle 91 percent.

The code's pages by instruction fetches over 100 running frames: `$80`
57 percent (the spin), `$81` 8.9, `$82` 4.3, `$F2` 3.9 (sound), `$8E`
3.0 (the engine, the pad, the buffer), `$C1` 2.3, `$E4` 2.1, then
`$8F`, `$F1`, `$AF`, `$9B`, `$EF`, `$E3`, `$C0`, `$DD`, `$BF` under
2 percent each: the game's working set is about forty pages of its
thirty-two kilobytes, the rest being data and states this run did not
reach.

## RAM

78,464 writes to 483 addresses in 100 frames: the zero page 27,642
(`$0000` alone 5,941: the scratch byte every routine shares, then
`$0007`, `$0004`, `$0006`, `$0008`, `$0005`, `$0002`, `$0003`), the
stack page 26,951 (`$01F3` to `$01FA`: the depth the tree reaches plus
the poll's own pushes), `$0200` 10,337 (the sprite page the DMA reads),
`$0300` 1,883 (the VRAM buffer), `$0400` 1,257, `$0600` 3,046 and
`$0700` 7,336 (the game's state), `$0500` 12.

## The VRAM pipeline

Nothing writes `$2007` outside the blank. The game logic fills a
buffer at `$0300` during the picture; the handler drains it at `$8EBB`
(`STA $2007`) after the DMA, then parks the address at `$3F00` and
`$0000` (four `$2006` writes) before rendering goes on. On a running
level the bursts come every four to five frames: 4 bytes to `$3F0C`
(a palette entry, the block animation), 3 bytes to `$207A` (the
timer's digits, nametable row 3 column 26), and, when the scroll has
crossed sixteen pixels, 26 bytes to a column of the other nametable
(`$2490`: rows 4 to 29 of one tile column). The scroll itself is two
`$2005` writes at line 31, `11` then `12` on consecutive frames as
Mario runs: one pixel a frame at this speed.

## From the pad to the jump

**The poll.** `$8E5C`, from the handler: for each port, `LDA $4016,X`
at `$8E6D` eight times, the byte accumulated on the stack (`PHA` at
`$8E6C`, the read, a shift, `PLA` at `$8E76`): 28 cycles a bit, 56
half-cycles between reads, against the pad cartridge's 16 cycles and
the menu's 19. The byte lands in `$06FC,X` (the buttons held) and,
after a pass through the stack, `$074A,X` (the buttons that changed),
`RTS` at `$8E91`. 16 reads a frame, the first 29 half-cycles after the
latch, at line 251.

**The readers.** The byte is read at `$819D` in the handler (a check
before the tree) and at `$AEED` in the game core, which copies it back
to `$06FC` and, at `$B109`, stores the A and B bits alone into the
zero-page temp `$0A`. At `$B47E` the player code loads `$0A`, and at
`$B484` `AND $0D` tests it against the previous frame's copy: a press
is A now and not A then.

**A tap in the air.** The first x-ray pressed A for one latch at latch
600, on top of the held Right, while the earlier jump was still in the
air. The records differ for four frames, 34 spans, then agree again to
the end: the poll's bytes, `$06FC`, `$074A`, `$0A`, the test at
`$B484`, and nothing the picture shows. The pictures of the two runs
at frames 615 to 632 are identical. The game ignored the press, and
the x-ray said so before the pictures did.

**A jump.** The second x-ray pressed A at latch 630 with Mario on the
ground. The same path to `$B484`, and from there a different code path
(2,529 fetches in the first stretch), the physics at `$F23D` to `$F260`
reading `$CE` and writing `$07`, a loop at `$9408` storing to `$06A1,X`
one index apart, and the player-state table at `$B34E` dispatching to
`$B376` instead of `$B35A`: the routine that ran only in the pressed
run, 746 half-cycles, the jump's own. Mario's sprite differs from frame
650 (a box of 16 by 31 pixels), the whole playfield from frame 664
(`$2000 <- 90` against `92`: the scroll crossed a nametable boundary
on a different frame, so the jump changed Mario's speed), and the
records never rejoin. 1,271 spans after the frame of the press: the
byte changed the run to its end.

## What the part confirms, and what it cannot

The part cannot show the fetches, but the effects are on its side:
the poll count (every latch eight clocks, held by `compare-logs.py` on
this cartridge), the picture at a trigger (E2's title at latch 300),
the frame at which the scroll moves, and the sound. The one claim here
the bench can test directly is the split: a capture triggered at a
running latch, decoded, must show the status bar unscrolled above line
32 and the level scrolled below it, on the same frame the model shows.
Done, below ("The split").

## Done on the part, the same night

**The poll's scanline** (`tools/poll-line.py`, `exercise/poll-line.txt`,
`exercise/menu-warm-poll.txt`): the latch line on scope channel two
beside the video on three, one capture holding fourteen polls, each
placed against the vertical sync before it with the line period
measured off the record's own horizontal syncs (63.500 us). The
measurement was made that night and read wrong on both sides, and
read right the afternoon after; both readings are kept here because
the wrong one is how the two errors were found.

That night: with the encoder's vertical sync (rows 245 to 247 from dot
0) the part's menu poll placed at PPU line 119.6 against the model's
120.15, and the game's at 250 against 251, the same six tenths of a
line on two screens. Neither number was right. The encoder's sync had
been authored at line granularity and never measured; asked
(`2c02`'s `vsync-probe`, the DAC's sync-tip leg every half-step through
a frame), the die begins its vertical sync where row 244's horizontal
sync begins, dot 280, and this record shows the same (the broad pulse
exactly one line after the preceding horizontal sync, 0.934 line long,
three a line apart), so the part's lines were 0.18 too high. And the
model's lines came from `dissect.py`'s arithmetic on the trace's dot
count, which numbered the pre-render line 0 and drifted a dot for
every dot a rendered odd frame skips: 0.3 line high at the menu's
frame 212 (and read from the menu's first two seconds, which poll half
a line later than the rest of it), 0.15 at frame 585.

The afternoon after, with the encoder held to the die (ntsc-crt
v0.2.10), `poll-line.py` placing the onset at 244 + 280/341, and the
model's positions read where its own strobe rises (`POSITIONS=1
pad-log`, the board recording the PPU's position at every `$4016`
write), not derived:

| screen | part, the rise (median of 14) | model, the rise (median over the same latches) |
|---|---|---|
| the menu, cold, five records at latches 554 to 568 | 119.375 (spread 0.08) | 119.358 (latches 294 to 308 and on; 119.83 for the first 127 latches, then this) |
| the menu, warm reset, latches 294 to 308 | 119.369 (spread 0.08) | 119.358 |
| the game, latches 554 to 568 | 250.733 (spread 1.7: the VRAM bursts) | 250.710 (spread the same) |

Two screens, two poll routines, and part and model agree to a
hundredth of a line on the menu and three hundredths in the game, the
strobe's rise 24 dots before its fall on both.

**The menu's first two seconds** (`exercise/menu-early-8.txt`, `-60`,
`-124`; runs `20260918-154203`, `-154311`, `-154424`, banked as
`menu-early-8/60/124`). The model's menu polls half a line later for
its first 127 latches (119.80 to 119.87) and at 119.36 from latch 127
on, so the part was asked the same, three channels at once: the
bridge's `TRIG` on channel one, armed before the reset because `RESET`
clears the bridge's trigger and the scope takes seconds to arm; the
latch on two; the video on three; 6 M points, the scope's depth with
three channels, seven polls a record. `poll-line.py --trig-ch 1`
numbers the polls from the pulse (the longest high run on the channel,
which also carries the pad's clocks as blips; latch n is the last rise
before it). Latch for latch against the model's own strobe positions:

| latches | part, the rise | model, the rise | largest difference |
|---|---|---|---|
| 7 to 12 | 119.81 to 119.89 | 119.79 to 119.87 | 0.10 line |
| 59 to 64 | 119.81 to 119.89 | 119.81 to 119.86 | 0.04 line |
| 123 to 126 | 119.81 to 119.89 | 119.80 to 119.85 | 0.09 line |
| 127, 128 | 119.375, 119.369 | 119.416, 119.349 | 0.04 line |

The part drops half a line at latch 127, the same latch as the model,
and no latch in the three records sits more than a tenth of a line
from the model's. Both sides wobble by 0.08 line from frame to frame
in the early stretch; the wobble is not the same latch for latch, and
nothing here says it should be (the model's runs in a period of
twelve latches; the part's was not read for a period).

**A finding on the way there, withdrawn.** Cold-powered by the relay,
the part's menu seemed never to take Start (nine runs: one latch, two,
a press at 400, a sixty-latch hold, two presses) while it took Select,
and took Start after a second reset. The byte reached the console
(the port's data line low in the fourth slot of the poll), the model
took the press cold with its RAM filled ten ways, and the difference
was put down to state a cold boot leaves. It was the head: its count
of the bridge's latches survived the bridge's `RESET`, so a `WAIT`
after a reset returned at once and the scope caught the menu before
the press (from `wait for latch` to `armed` in those runs' logs is the
three seconds the arm takes; in the one that "took", 12.8 s). With the
count cleared on the bridge's acknowledgement, the press takes with no
reset, one and three (runs 193915, 194105, 194257), the poll at the
title's lines 247 and 249. The account is in `open-items.md`. The
menu's logic read from the model's record stands: a press that arms a
mask and a release that fires the switch, Select another way.

**The split** (`tools/split-score.py`, `exercise/split.txt`, run
`20260918-135721`, the afternoon after). The game reached by the
warm-reset recipe (two resets, then the press: at the time the only
way that seemed to work, see above), Right held from latch 520, the scope stopped on the
bridge's `TRIG` at latch 600 with the video on CH3: eight frames of
Mario walking right. The measurement is the one the claim above asks
for, made without telling either side where the split is: every
picture row's horizontal shift between two frames two apart, from the
decoded luma (the peak of the row's cross-correlation, interpolated,
in dots), on the part's record and on the model's frames. A row of
the status bar does not move; a row of the level moves by the
scroll's advance; a row with nothing on it has no answer and is
reported flat. Part and model gave the same picture row for row: rows
15 to 32 still (the bar's text, with the comb's reach one row past
it), rows 33 to 46 flat (sky above the first cloud), rows 47 down
moving, 1.94 dots on the part against 1.89 on the model over two
frames, 4.34 against 4.30 over four, and the same flat bands through
the level (73 to 142, 161 to 173). So the bar is unscrolled through
row 32 and the level scrolled from row 47 on both, and the split lies
between: the fourteen flat rows are the picture's, and no measurement
of this frame can put it tighter than that. The dissection's line 31
write, taking effect from row 32, is inside the bracket.

The third comparison, the part's triggered frame against the model's
F-1 to F+2 (the bar's rows giving the constant offset between the two
pictures, the level's rows the scroll beyond it), named the model's
**F+1** under the rule the tools had that afternoon: the level sat
1.27 dots further on than the model's F, 0.11 from its F+1. That was
the trigger convention, not the game. The rule took the picture after
the frame the latch fell in, which is right for a game that polls at
the top of the blank; this one polls at line 250, after the vertical
sync's onset (row 244 dot 280), so the trigger lands past that frame's
sync, the recovery anchors on the next one, and the picture it hands
back is the one after that. `Console::run_to_picture_after_latch` now
decides from the latch's recorded position (nes @ efbcc46,
`tests/latch_frame.rs`, its onset pinned a dot either side and
MUTATE=1 red), `capture-score` and `split-score` share it, and this
record names **F+0**, the level 0.11 dots beyond the bar. E2's title, a
still picture, could not have shown the difference; a scrolling frame
did at once. The synthetic roundtrip (the part synthesised from the
model's own frames) holds to the same bracket, the same advance within
a quarter dot and F, and goes red when synthesised one frame late or
from one frame twice.

## What it seeds

Five patterns for the encyclopedia, each with numbers on it: the game
loop inside the interrupt with the NMI guard; the sprite-0 split for a
status bar; the VRAM buffer drained in the blank; the jump engine
(pull-and-jump through a table after the `JSR`); the state dispatch
(a table indexed by the player's state). And one method: a routine
tree diffed between two runs one byte apart names the routine that
belongs to an action without reading a line of its code.
