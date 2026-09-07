# The bench script

One text file drives a run on the head (`head/headd.py`, sent by
`tools/bench.py run`) and, with the same words, the model
(`nes-console`'s `pad-log` takes the `AT` lines). A line is a word and
its arguments; `#` starts a comment. Latch indices count the console's
controller strobes since the last `RESET`, from zero, which is the
index the bridge's log and the model's log share.

| line | on the head | on the model |
|---|---|---|
| `RESET` | zero the bridge's counters, then pulse the reset relay | the console powers on at latch zero |
| `POWER ON` / `POWER OFF` | the power relay | nothing |
| `MODE PASS` / `MODE INJECT` | passed to the bridge: the original pad's byte, or the scripted one | the model has no pad in hand: `INJECT` is the only mode |
| `SET hh` | the byte to hold now (bit 0 = A, set = pressed) | the byte from the start |
| `AT n hh` | from latch n on, hold hh; written after latch n-1 so it is in the register at latch n | the controller's schedule, applied at the strobe's rise before latch n |
| `TRIG n` | the bridge raises EXT TRIG at latch n | nothing (the model renders the frame at n directly) |
| `ARM name [ch] [scale] [offset]` | the scope set for a single shot on EXT TRIG; the capture is `name.u8` with `name.toml` beside it | nothing |
| `CAPTURE` | wait for the armed trigger and read the record (a `WAIT` past the trigger does this too) | nothing |
| `WAIT n` | until the bridge has logged latch n | run to poll n |
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
ARM game-t300 3 0.5 -1.3
TRIG 300
WAIT 320
CAPTURE
```

The head writes the run to `runs/<stamp>/` (`script.txt`, `head.log`
with each line as it played, `bridge.log` with every line the bridge
printed, the captures) and `bench.py` fetches it. `compare-logs.py`
diffs `bridge.log` against `pad-log`'s output for the same script.
