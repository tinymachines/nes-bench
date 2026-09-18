# The bench script

One text file drives a run on the head (`head/headd.py`, sent by
`tools/bench.py run`) and, with the same words, the model
(`nes-console`'s `pad-log` takes the `AT` lines). A line is a word and
its arguments; `#` starts a comment. Latch indices count the console's
controller strobes since the last `RESET`, from zero, which is the
index the bridge's log and the model's log share.

| line | on the head | on the model |
|---|---|---|
| `RESET` | zero the bridge's counters, then pulse the reset relay | the console powers on at latch zero (`pad-log`); `bench-script` holds the CPU's /RESET for the head's half second and releases it, the warm reset |
| `POWER ON` / `POWER OFF` | the power relay | nothing |
| `MODE PASS` / `MODE INJECT` | passed to the bridge: the original pad's byte, or the scripted one | the model has no pad in hand: `INJECT` is the only mode |
| `SET hh` | the byte to hold now (bit 0 = A, set = pressed) | the byte from the start |
| `AT n hh` | from latch n on, hold hh; written after latch n-1 so it is in the register at latch n | the controller's schedule, applied at the strobe's rise before latch n |
| `TRIG n` | the bridge raises EXT TRIG at latch n; put it after the `ARM`, which takes seconds | nothing (the model renders the frame at n directly) |
| `ARM name [channels] [scale] [offset] [source] [s/div] [depth]` | the scope set for a single shot: channels `3` or `1,2,4`, the trigger from a channel (`CH1`, where the bridge's TRIG line sits; the DS1054Z has no EXT input, and `EXT`, the old default, is refused by name), the timebase and the memory depth (12 M points with one or two channels, at most 6 M with more); the capture is `name.u8` (one channel) or `name-chN.u8` (several) with `name.toml` beside them naming the rate and the trigger's sample | nothing |
| `CAPTURE` | wait for the armed trigger and read the record (a `WAIT` past the trigger does this too) | nothing |
| `WAIT n` | until the bridge has logged latch n since its last `RESET` (the head clears its count on the bridge's `# reset`; before 2026-09-18 it kept the last session's, and a `WAIT` after a `RESET` could return at once, `open-items.md`) | run to poll n (`bench-script` counts from each `RESET`, as the bridge does) |
| `WAIT s S` | seconds | nothing |

A B1 script, as the plan describes it:

```
POWER ON
WAIT 2 S
MODE INJECT
SET 00
RESET
AT 120 08          # Start, from poll 120
AT 122 00
ARM game-t300 1,3 0.2 -0.5 CH1   # the video on CH3 at 200 mV/div, the trigger line on CH1 beside it
TRIG 300
WAIT 320
CAPTURE
```

The head writes the run to `runs/<stamp>/` (`script.txt`, `head.log`
with each line as it played, `bridge.log` with every line the bridge
printed, the captures) and `bench.py` fetches it. `compare-logs.py`
diffs `bridge.log` against `pad-log`'s output for the same script.

A B2 script, one power-on (`tools/b2-align.py sweep` plays it N times
and classifies each run):

```
POWER OFF
WAIT 3 S
ARM align 1,2,4 1.0 -2.0 CH4 0.0005 1200000   # master clock, M2, ALE; triggered on ALE's first rise, when rendering starts
POWER ON
CAPTURE
POWER OFF
```
