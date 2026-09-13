# 2026-09-13: the pad cartridge, re-exported for the flashcart

**Outcome:** open. The cartridges are exported, checksummed, on the Pi and
served; the flashcart's copy is yours to write, and the checksum says
whether it is this one.

## Why

The family's test cartridge now sets its stack pointer at reset
(`LDX #$FF; TXS`, `nes` @ 513bf39). The stack pointer powers on
undefined: the 2A03 die's measured $BD, the 6502 die's $FD, and a record
of one replayed on the other parted at the first NMI's push. Every real
program has the line; ours did not. It moved the first poll by three
bytes' worth of cycles, so the model's prediction for the part changed:
597 polls over 600 frames, not 596, the nines unchanged at 21 with the
DMC looping. Sitting 5's compare-logs holds the bridge's log to that
figure, so the flashcart must carry this cartridge and not the one from
before.

## The files (MEASURED 2026-09-13, exported from `nes` @ 5214e36)

| file | bytes | sha256 | body crc32 | the model's count |
|---|---|---|---|---|
| `pad.nes` | 40976 | `7eba0e4cf936683e979a2e0dd3bf6fca6bb5bd664c6ac14861d6589bfd0ce34e` | `599C4188` | 597 polls over 600 frames, every one eight reads |
| `pad-dmc.nes` | 40976 | `a61677076e9c3e634b7dc153f6889f56f4965d173a31cfe58e8c6cc54e45b9d6` | `2BD30315` | 597 polls, 576 of eight reads and 21 of nine (the DMC's fetch landing on a poll) |
| `pad-paint.nes` | 40976 | `06bf901f475b5a60c6faf4d6a2d52981e7830319872a22646298baa7eb78a284` | `3155F514` | as `pad-dmc`, painting the polls |
| `bars.nes` | 40976 | `93150c0ab5579deded8f61a3e4f9bfeac22473b3ce8d86d9b8339788e313cfd7` | `25D60AE9` | unchanged (its program is its own); served since N6 |

The counts are `pad-log <rom> 600 script` with `SET a5` in the script,
the same line compare-logs prints from the part. `599C4188` is also the
record's stamp on every window the 6502 site carries
(`6502.tinymachines.ai/windows/`), so the cartridge on the flashcart,
the one the model traced, and the one the die ran are one file.

## Where they are

- **the tools:** `roms/` in this checkout (gitignored: `export-testrom
  <out> pad|pad-dmc|pad-paint|bars` in `nes` regenerates them) with
  `SHA256SUMS` beside them.
- **the head:** the same four files and the sums at `~/nes-bench/roms/`
  on the Pi, verified there with `sha256sum -c SHA256SUMS`.
- **the site:** `tinymachines.ai/nes/pad.nes` and `/nes/pad-dmc.nes`
  beside `/nes/bars.nes`, exported at the boarded console commit and
  hash-checked by the build (`data/nes.json`, `console.cartridges`,
  carrying the same counts).

## The steps

1. **you:** take `pad.nes` and `pad-dmc.nes` from the site or the Pi
   onto the flashcart's card (and `bars.nes` with them: the M4 bars gate
   still wants it on a console).
2. **you:** before writing, check the sum on whatever machine holds the
   card: `sha256sum pad.nes` must print the table's.
3. **you:** at sitting 5, say which of the two the console runs; the
   bridge's log and the model's are compared latch for latch, and the
   count above is the number the comparison is held to.

## Observations

(none yet)
