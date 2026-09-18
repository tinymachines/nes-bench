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
| 241 | 98 | NMI vector taken | `$8082` |
| 241 | 149 | `$2000 <- 10`: NMIs off, nametable 0 | |
| 241 | 233 | `$2001 <- 06`: rendering off for the blank's work | |
| 241 | 245 | `$2002` read: the status cleared | `$80A6` |
| 241 | 281 | `$2005 <- 00, 00`: the scroll zeroed for the status bar | |
| 241 | 323 | `$2003 <- 00`, then `$4014 <- 02`: sprite DMA from `$0200` | |
| 242 | 2 | the DMA's 256 writes of `$2004`, to line 246 dot 178 | |
| 246 | 262 | `$2002` read, the VRAM buffer drained (none this frame) | `$8EDD` |
| 246 | 301 | `$2005 <- 00, 00` | |
| 247 | 107 | `$2001 <- 1e`: rendering on | |
| 251 | 210 | the pad polled, latch 585, 16 reads (both ports) | `STA $4016` at `$8E63` |
| 256 | 267 | a scan of `$0780,X` downward, ten steps | `$810E` |
| 2 | 147 | `$2002` read once: the sprite-0 flag seen clear | `$813D` |
| 16 | 322 | `LDA $2002 / AND #.. / BEQ` spun 171 times: waiting for sprite 0 | `$8150` |
| 30 | 165 | the hit; `DEY / BNE` 19 times, a delay into the blank | `$8159` |
| 31 | 173 | `$2005 <- 11, 00`: the level's scroll set below the status bar | |
| 31 | 230 | `$2000 <- 10`: the nametable for the level | |
| 31 to 87 | | the game's logic: the operation-mode tree | `$8212` from `$8175` |
| 87 | 283 | `$2002` read, `$2000 <- 90`: NMIs on | `$8178` |
| 88 | 0 | `RTI`, and the spin at `$8057` until line 241 | `$8181` |

So the blank is spent on the DMA, the VRAM buffer and the sound and
pad routines; the top of the picture is spent waiting for the sprite-0
hit at the bottom of the status bar (lines 16 to 30, the bar being 32
lines tall); the scroll for the level is written at line 31, which is
the split; and the game's own logic runs during the visible frame from
line 31 to about line 87. A frame that loads a column of the next
screen (frame 615: 26 bytes to `$2490`) puts rendering on at line 252
instead of 247 and ends its handler at line 108; the logic's budget is
what is left of the picture.

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

## Done on the part, the same night

**The poll's scanline** (`tools/poll-line.py`, `exercise/poll-line.txt`):
the latch line on scope channel two beside the video on three, one
capture holding fourteen polls, each placed against the vertical sync
before it with the line period measured off the record's own
horizontal syncs (63.500 us). On the multicart's menu every one of the
fourteen rises 136.55 lines after the sync's first row, a spread of
0.08 line; with the encoder's sync rows (245 to 247) that is PPU line
119 dot 188. The model's menu polls at line 120 dot 50, on every
frame. In the game (a run that reached it, below) the part's poll
rises at line 250 on twelve frames of fourteen, 251 and 252 once each;
the model's falls at 251 on 68 frames of 100 and later on the rest.
Two screens, two poll routines, and the same six tenths of a line
between part and model both times: a constant, which is what an
encoder's line-granular vertical sync would leave, and which the
switch-level PPU can settle by saying on which dot its sync begins.
The game's two extra values on the part are the frames a VRAM burst
pushed the poll, as the model's spread is.

**A finding on the way there.** Cold-powered by the relay, the part's
menu takes Select (the cursor moved to Duck Hunt, seen in the decoded
capture) and never takes Start: one latch, two latches, a two-second
or ten-second warm-up, a press at latch 400, a sixty-latch hold, two
presses in a row, nine runs on the menu's own poll line every time.
The byte reaches the console: with Start injected, the port's data
line reads low in the fourth slot of the poll. After a warm reset
(power, five seconds, reset, five seconds, reset, then the press) the
same press takes, as E2's did on a console that had been running for
an hour. The model takes it cold, and with its work RAM filled with
00, ff, 55, aa and six seeded random patterns (the `[ram]` knob built
for this), still at frame 212 every time. Read from the model's
record, the menu's logic is a press that arms a mask and a release
that fires the switch; Select goes another way. What a cold boot
changes that a warm reset does not, and RAM does not, is in
`open-items.md`; the state-showing cartridge and the logic analyser
are what close it.

## What it seeds

Five patterns for the encyclopedia, each with numbers on it: the game
loop inside the interrupt with the NMI guard; the sprite-0 split for a
status bar; the VRAM buffer drained in the blank; the jump engine
(pull-and-jump through a table after the `JSR`); the state dispatch
(a table indexed by the player's state). And one method: a routine
tree diffed between two runs one byte apart names the routine that
belongs to an action without reading a line of its code.
