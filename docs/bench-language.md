# The bench's language

A handoff: everything a newcomer (a person or an agent) needs to drive
the NES bench, read what it says back, and work the way it has been
worked. Written 2026-10-17, the day every feature below was exercised
end to end through the Pi.

Every word here is marked **built** (it exists, and was played on the
part) or **proposed** (a name for something the bench cannot do yet).
Nothing proposed is described as if it ran.

## The machine in one picture

```
            workstation                         bench Pi (the head)                    console
  ----------------------------      ---------------------------------------      -----------------
  the model (nes-console)           headd.py  UDP 6530 / HTTP 6531
  the comparators                     |-- GPIO27 --> K1 relay ------------------> power switch
  bench.py  ---- UDP JSON ---->       |-- GPIO17 --> OK1 opto ------------------> reset button
                                      |-- USB serial 115200 --> UNO bridge -----> controller port 1
                                      |-- LAN SCPI 5555 --> DS1054Z scope <------ video, latch, D0, TRIG
                                      `-- USB --> Roxio grabber <---------------- video (splitter)
```

Three inputs (**pad**, **power**, **reset**), three outputs (**screen**,
**scope**, **sound**, the last not yet wired). One clock everything is
counted in: the **latch**.

## The unit of time: the latch

The console reads its controller by raising OUT0 (the **latch**, 3.6 us
wide) and then clocking eight bits out on D0. Super Mario Bros. and
Duck Hunt do it once per frame, **60.1 times a second**, measured on the
bench at 1,203 in 20 s. The bridge counts these rises from its last
`RESET`, starting at 0, and the model counts the same ones.

So **latch n** is the bench's tick. It is a frame for these games, but
it is defined by the poll, not by the picture: a game that polls twice
a frame ticks twice, and a game that is not polling does not tick at
all (a hung console, a cart that did not boot, the power off).

Two consequences that matter for everything below:

- **Scripts are written in latches, not seconds**, which is why the
  same script replays exactly on the part and on the model.
- **Seconds exist only on the head** (`WAIT s S`), for the things that
  are not the game: the console booting, a relay settling.

## Inputs

### The pad byte

One byte, set bit = pressed, in the console's own order (the one fact
lives in `nes_glue::controller::Buttons::as_byte`):

| bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|---|---|
| button | Right | Left | Down | Up | Start | Select | B | A |
| alone | `80` | `40` | `20` | `10` | `08` | `04` | `02` | `01` |

Bytes worth knowing by sight: `00` nothing, `08` Start, `04` Select,
`80` walk right, `82` run right (Right+B), `81` jump right, `83` running
jump, `40`/`42` the same leftward.

How it reaches the console (built, walked 15 of 15 on 2026-10-17): the
UNO shifts the byte (complemented: the port is active low) into a
74HC595 over SPI and moves it to the outputs with one RCLK edge, only
while the latch is low. The 74HC165 loads the 595's outputs while the
latch is high and the console clocks them out on D0. The byte in force
at a latch is the byte that latch reads, all eight bits at once; a byte
can never tear across a poll.

### Power and reset

| hand | wire | high | measured |
|---|---|---|---|
| power | GPIO27 through K1, across the front panel's switch | console on | the polls stop for 2.5 s and resume |
| reset | GPIO17 through OK1, across the reset button | reset held | the polls stop for 1.75 s and resume |

The console's own power switch must stay OFF, or K1 cannot turn it off.
The head holds reset at least 0.5 s (`RESET_HOLD_S`: shorter holds were
measured not to take). Both pins rest low at boot.

## Outputs

| output | instrument | what it gives | status |
|---|---|---|---|
| the poll log | the bridge | one `L` line per latch: the byte read and its clock count | built |
| the scope | DS1054Z over SCPI | a triggered record, 12 M points at 50 MSa/s, any of four channels | built |
| the screen | Roxio grabber on the Pi | a 720 x 480 JPEG of the picture, about a second to take | built, not a script word |
| sound | C-Media input on the Pi | the console's audio | **proposed**: nothing is wired (`open-items.md`: it needs an attenuator first) |

The scope's channels, as wired (`cheat-sheet.md`):

| channel | carries | use |
|---|---|---|
| CH1 | the bridge's TRIG line | the trigger (the DS1054Z has no EXT input) |
| CH2 | OUT0, the latch | where the poll falls in the frame |
| CH3 | composite video, through the splitter | the picture, decoded by ntsc-crt |
| CH4 | D0, the bits the console reads | the walk: the byte as the console saw it |

## Layer 1: the bridge's words (the Pi to the UNO, serial)

Lines of text, 115200 baud. All **built** (`firmware/bridge-uno`).

| word | does |
|---|---|
| `MODE PASS` | the original pad on the bridge's own port drives the console (the default at boot) |
| `MODE INJECT` | the bridge drives the console with the byte it is given |
| `SET hh` | hold `hh` now |
| `AT n hh` | from latch n on, hold `hh`; in increasing n; 600 held at once, an applied one freeing its slot (`# late AT n at latch L` if n has passed) |
| `TRIG n` | raise the trigger line at latch n, for a millisecond |
| `RESET` | zero the latch count, clear the schedule and the trigger (not the console: that is the head's) |
| `STATUS` | mode, counts, the byte held, deferred and torn writes, spare stack |
| `MUTATE ON` / `OFF` | feed the clock counter the latch line: the clocks-per-poll check must go red |

What it says back:

| line | means |
|---|---|
| `L n hh c` | latch n read byte `hh`, and the console clocked `c` bits (8 for a normal poll) |
| `# ...` | an answer or a warning (`# schedule full`, `# the load window opened across an RCLK edge`) |

## Layer 2: the head's script (a run)

A text file, one word a line, `#` a comment, sent with
`tools/bench.py <head> run script.txt`. The head plays it top to bottom
and writes `runs/<stamp>/`. All **built** (`docs/script.md` is the
reference; this is the summary).

| word | does | timing |
|---|---|---|
| `POWER ON` / `POWER OFF` | GPIO27 | immediate |
| `RESET` | hold the console in reset (GPIO17), zero the bridge; released at the first word that is not `MODE SET AT TRIG ARM` | latch 0 is the first poll after the release |
| `MODE`, `SET`, `AT`, `TRIG` | passed to the bridge, each answer checked | `AT` loads before it is due; a `TRIG` already past stops the run |
| `ARM name ch scale offset source [s/div] [depth]` | set the scope for one shot | seconds: put it before its `TRIG` |
| `CAPTURE` | wait for the trigger, read the record into `name.u8` and `name.toml` | about a minute to read 12 M points |
| `WAIT n` | until the bridge logs latch n | the **NOP of the game's clock** |
| `WAIT s S` | sleep s seconds | the **NOP of the wall clock** |

### Idioms

Everything else is a pattern of the words above.

| idiom | lines | why |
|---|---|---|
| tap a button | `AT n hh` / `AT n+2 00` | two polls held: games act on the press edge, and one poll can be missed |
| hold a button | `AT n hh` ... `AT m 00` | m - n polls of walking, running |
| a jump of a chosen height | `AT n 83` / `AT n+k 82` | Super Mario Bros. jumps higher the longer A is held, so k is the height |
| a clean start | `POWER ON`, `WAIT 5 S`, `MODE INJECT`, `SET 00`, `RESET`, `WAIT 5 S`, `RESET` | the warm-reset recipe the game scripts start with (`split.txt`, `e2-title-warm.txt`) |
| into Super Mario Bros. | Start at 200, Start again at 330 | the menu, then the title |
| into Duck Hunt | Select at 200, Start at 240, Start at 600 | the cursor, the menu, the title (a press before about 500 is ignored there) |
| a picture at latch n | `ARM name 1,3 0.2 -0.5 CH1`, `TRIG n`, `WAIT n+20`, `CAPTURE` | video on CH3 at 200 mV/div, the trigger on CH1 |
| the poll against the picture | `ARM name 2,3 0.2 -0.5 CH2`, `CAPTURE` | the latch on CH2 beside the video |

### What a run leaves

| file | holds |
|---|---|
| `script.txt` | the script as received |
| `head.log` | every word as it played, with the wall time |
| `bridge.log` | every line the bridge printed: the `L` stream is the run's ground truth |
| `name-chN.u8` + `name.toml` | a scope record and its rate, trigger sample and channel scales |

Runs live on the Pi (`~/runs`). The comparators run on the workstation,
which has the model and the ROMs, so a run is pulled before it is
scored (`rsync`, or `bench.py fetch`).

## Layer 3: the head's live ops (UDP JSON)

**Built.** `tools/bench.py <head> <op>`, or one JSON datagram to port 6530.

| op | does |
|---|---|
| `status` | the head, the bridge's last latch, the scope, the power, the run playing |
| `run` | start a script; refused while one plays |
| `abort` | stop the run playing |
| `bridge "LINE"` | one bridge line now, its answers back (works between runs: `SET 80` live) |
| `runs`, `fetch <stamp>` | list and pull run directories |
| `pad on` / `off` | a Bluetooth gamepad paired to the Pi becomes the byte; the session is a run, so it is a recording |

## Layer 4: the tools around a run

| tool | where | question it answers |
|---|---|---|
| `bench-check.py --hands head` | Pi | is the bench whole: bridge, scope, polls, trigger, the walk, reset, power |
| `rig-check.py` | workstation, Pi cameras | has the breadboard moved since the baseline (none taken yet) |
| `compare-logs.py part model` | workstation | do the part and the model read the same byte at every latch |
| `b1-score.py run rom name` | workstation | does the captured picture match the model's frame, region by region |
| `split-score.py` | workstation | where down the picture the scroll starts, both sides |
| `poll-line.py` | workstation | which scanline the poll lands on |
| `eyes.py pair` / `compare` | workstation, Pi grabber | do the grabber and the scope's decode agree |
| `b3.py record` / `replay` / `bisect` | workstation | turn a hand's play into a script; replay it; find the first latch the model and part disagree |
| `xray.py rom name --latch n --byte hh` | workstation, model only | what one byte at one latch changes inside the machine |
| `scripts/grab.sh screen` | Pi | one picture off the grabber, now |

## The workflow

Every piece of bench work since 2026-09-18 has the same four parts,
named in `exercise.md`: a **script** (what the hands do), a **model
run** of the same script, a **comparator** that sets the two side by
side, and a **gate** stated before it runs. A run is one playing of a
script, stamped. The habits that came with it:

1. **bench-check first.** Every session starts green or finds out why
   not. On 2026-10-16/17 it found four faults in a row: the scope off
   the network, the serial unit asking for a moved device, R2 one row
   off the clock lead, and the reset opto miswired.
2. **Write it in latches.** If a step needs seconds, it is not the
   game's step.
3. **The poll log is the truth.** Before believing a picture, read
   `bridge.log`: did the console read the bytes, at the latches, for
   the polls the script said.
4. **The model is the rehearsal.** A script plays on the model first;
   the part is where it is checked. The model and the part agreed on all
   2,301 latches of the E3 replay on 2026-10-17.
5. **A comparator that cannot fail tests nothing.** Every one here has a
   `MUTATE` that must go red.

## Learning to play: what the language implies

A decision through the head takes about a second and a half (a grabber
frame, then a `bridge` op), which is about ninety polls. Super Mario
Bros. does not wait that long. So the bench is an **open-loop** player:

- **Plan on the model.** It runs the same script deterministically and
  far faster than real time, and it can be searched: try a schedule,
  read where Mario ended up, change a latch, try again.
- **Play the plan on the part** in one run, as a schedule.
- **Check it** with the poll log (the bytes went in), a grabber frame
  or a scope capture at chosen latches (the picture), and
  `compare-logs.py` (the part did what the model did).
- **When they part**, `b3.py bisect` finds the first latch that differs.

The UNO holds **600 schedule entries** at once, a ring since 2026-10-18:
the head loads what fits before the console leaves reset and streams
the rest as the latches go by, so a run is no longer bounded by it (a
minute of a human's play was 289; a planned run from power-on to 2-2,
258). A streamed run takes no scope capture mid-run: reading the record
blocks the feed for about a minute.

**Built 2026-10-17, for Super Mario Bros.:** `tools/plan.py` searches in
segments of 30 latches, thirteen moves each (run, walk, stop, back, and
a running jump at three points with three heights), every candidate on
the model through `nes-console`'s `watch` example (the script played as
the head plays it, with chosen RAM bytes at every latch), six at a time,
and backs up a segment when every move dies. It cleared 1-1 on the model
with four backtracks: a 71-entry schedule, the flagpole at latch 2190.
Played on the part through the head (run 20261017-224132), the grabber's
frames at 700, 1300, 1900 and 2200 show the same run reaching the
flagpole. The same day the planner moved onto the model's saved states
(`nes-console`'s `branch` example, a load proven byte-identical to the
run that never stopped): a candidate costs its own latches, about 0.6 s
against ten, 1-1 replans in under six minutes, and 1-2 planned in eight
from the end of 1-1's schedule. 1-2 taught four rules now in the tool:
jumps every five latches, a latch backed out of four times gives up the
segment before it, a lookahead that ends with the game holding Mario (a
pipe) runs on until he is free, and a segment that saw him held is no
stall. Played on the part (run 20261017-235518), one schedule of 132
entries took the console through both flagpoles to "WORLD 1-3" with no
life lost. 1-3, the treetops, added two more: a move is kept only if one
of its continuations lives (a gentler rule committed Mario to a gap he
was already falling into), and a level found done in the lookahead keeps
the continuation that found the flagpole (without it the schedule
stopped short and Mario stood at the end, alive). Run 20261018-012133:
power-on to "WORLD 1-4" on the part, 172 entries, no life lost. 1-4, the first castle, ends at an axe
and not a flagpole: the axe turns $0770 to 2 and the next world follows,
so either now counts as done. Run 20261018-021108: power-on to "WORLD
2-1" on the part, Bowser into the lava, 197 entries. The attempt before
it (20261018-020509) stopped at the start: after the second reset the
console polled once and no more, with the bridge healthy; the retry
with the same reset timing ran clean. That is the second failed console
start in two days, open in `open-items.md`'s terms: not yet understood. 2-1 needed nothing new: planned in under
fourteen minutes, run 20261018-023103 took the part to "WORLD 2-2",
258 entries. 2-2, the water, needed swimming
(A tapped every 10 or 16 latches, measured first: steady taps hold
Mario near the surface, none sink him), ties broken toward fewer
entries, and one more scoring rule: a pipe taken counts above x, since
past 2-2's exit pipe Mario lands at a smaller x in the same area and
every pipe move had scored as going backwards. Run 20261018-031731:
power-on to "WORLD 2-3", 370 entries. 2-3, the long bridge, needed nothing new:
planned in under ten minutes, run 20261018-034339 to "WORLD 2-4", 404
entries. 2-4, the second castle, needed nothing new either:
seven minutes, run 20261018-040301 to "WORLD 3-1", 435 entries. 3-1
was the first plan past the head's room: 492 entries, the last dozen
streamed from latch 19990 while the game played, run 20261018-042415 to
"WORLD 3-2", every one of its 21,693 polls in the log and none wrong. 3-2:
548 entries, run 20261018-044744 to "WORLD 3-3", 24,093 polls, none
wrong. 3-3, the mushroom tops, needed a beam (`--beam 4`: the way on
was up, and depth first had dropped that route); run 20261018-061315 to
"WORLD 3-4", 587 entries. 3-4, the third castle, found a fault in the
model: `branch`'s `RUN` stopped at the end of a frame, and a frame that
held two polls let the second fall before the planner gave its byte, so
the first plan failed its straight replay. `RUN` now stops on the poll
and a late `AT` is refused, as the bridge refuses one; replanned, run
20261018-145621 to "WORLD 4-1", 618 entries, 27,683 polls, none wrong.
4-1, Lakitu's, needed nothing new: 662 entries, run 20261018-162219 to
"WORLD 4-2", 30,072 polls, none wrong. 4-2 defeated five plans and
gave the planner most of its present words (below); its last tall pipe
was crossed by a route searched by hand on the model and spliced onto
the beam's own stair-top state, and the planner went on from there.
730 entries, run 20261018-234630 to "WORLD 4-3", 33,502 polls, none
wrong. 4-3, the mushroom tops and falling lifts, the beam crossed on
its own: 767 entries, run 20261019-015500 to "WORLD 4-4", 35,501
polls, none wrong. 4-4, the first maze, sends Mario back unless he
stands at the heights the game's own table wants at two pages; the
planner now reads that table out of the game, and crossed the first
check on its own. The second is entered through a one-tile gap that
running right goes over, and that stretch was searched by hand on the
model and spliced on: 796 entries, run 20261019-065615 to "WORLD
5-1", 37,793 polls, none wrong. 5-1 the beam crossed on its own: 845
entries, run 20261019-081032 to "WORLD 5-2", 39,951 polls, none wrong.
5-2 too, above ground the whole way: 902 entries, run 20261019-094241
to "WORLD 5-3", 42,112 polls, none wrong. 5-3 the same: 944 entries,
run 20261019-104805 to "WORLD 5-4", 44,023 polls, none wrong. And
5-4, World 5's castle: 975 entries, run 20261019-115112 to "WORLD
6-1", 45,892 polls, none wrong. 6-1, Lakitu at night: 1,015 entries,
run 20261019-130306 to "WORLD 6-2", 47,971 polls, none wrong. 6-2,
above ground the whole way: 1,102 entries, run 20261019-144503 to
"WORLD 6-3", 50,393 polls, none wrong. 6-3, lifts and Bullet Bills:
1,138 entries, run 20261019-160009 to "WORLD 6-4", 52,202 polls, none
wrong. 6-4, World 6's castle: 1,169 entries, run 20261019-172628 to
"WORLD 7-1", 54,022 polls, none wrong. One schedule now plays from
power-on through twenty-four levels, six castles and the water, with no
life lost.

The planner's words, as `tools/plan.py` takes them:

| option | does | from |
|---|---|---|
| `--prefix S --first n` | plays the bench script S on the model to latch n and searches on from there | 1-2 |
| `--swim` | adds the water's moves, A tapped at steady rates | 2-2 |
| `--beam B` | keeps B distinct positions a segment instead of searching depth first | 3-3 |
| `--beam-high H` | gives H of the beam's B to the highest positions reached standing | 4-2 |
| `--no-ceiling` | standing on the top row counts as a death (the way over a ceiling to a warp zone) | 4-2 |
| `--resume STATE` | goes on from a saved beam state; the `.json` beside each holds its latch and the schedule that reached it | 4-2 |
| (always, in a castle maze) | the game's maze checks read out of its code; the `--beam-high` slots go to the move whose lookahead stands furthest on at the height the next check wants | 4-4 |

And its rules, always on: a level is done at the flagpole (`$000E` 04
or 05), at the axe (`$0770` 2) or when the level changes to the next
one; a change to any other level is a warp and counts as a death, and
so is x jumping more than a page while Mario is his own (a maze sending
him back); a move is kept only if one of five ways on lives (run, jump at once,
jump a little later, wait then jump, and keep A held, which carries a
jump across the segment's end). The level by level account,
with a drawing of each, is `docs/plan-log.md`.

## Proposed words

Names for what the bench cannot do yet, so a script can be written
against them when they are built. None of these exist.

| word | would do | needs |
|---|---|---|
| `GRAB name n` | a grabber frame at latch n, filed in the run | a head word around `grab.sh`, timed off the `L` stream |
| `EARS name s` | s seconds of the console's audio, filed in the run | an attenuator into the C-Media input, then the head word |
| `TAP btn n` / `HOLD btn n m` | the idioms above by button name | a preprocessor in `bench.py`; the bridge's words stay bytes |

## Glossary

| term | means |
|---|---|
| the part | the real console on the bench, as opposed to the model |
| the model | `nes-console`: the switch-level CPU and PPU running the same ROM |
| the head | `headd.py` on the bench Pi: the one process that owns the hands and the instruments |
| the bridge | the UNO and its two shift registers between the Pi and the controller port |
| the hands | power (K1) and reset (OK1); the pad is the third |
| latch | one poll of the controller; the bench's tick, about a frame |
| `L` line | the bridge's report of one latch |
| run | one playing of a script, a stamped directory |
| step | a script, a model run, a comparator and a gate, named (E0 to E5 in `exercise.md`) |
| the walk | bench-check's test of fifteen bytes read back off D0 |
| the warm-reset recipe | power, reset, five seconds, reset again: how every scripted game starts |
| injection | `MODE INJECT`: the bridge, not a hand, is the pad |
| the trigger | the bridge's TRIG line, which stops the scope at a chosen latch |
| a window | a span of a run cut for the 6502 site's pages to stand inside |
| the x-ray | two model runs one byte apart, diffed half-cycle by half-cycle |
