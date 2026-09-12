# Eyes versus scope: the grabber's picture against the decoded signal

Added 2026-09-12. The console's composite goes two ways at once: to
the scope (CH3, the record the family's decoder works from) and to the
Roxio grabber on the Pi (`head/roxio-em28xx/`, a TV chip's own decode).
`tools/eyes.py` takes both together and scores them on the console's
256 by 240 pixel grid.

```
python3 tools/eyes.py pair --scope <ip> --pi <host> <name>   # both captures, together
python3 tools/eyes.py compare <name>                          # decode, align, score
```

`pair` sets the scope up as ntsc-crt's capture tool does (its setup
saved and restored), asks the Pi for eight grabber frames through
ffmpeg, and stops the scope the moment they are in: the record's last
240 ms end within a millisecond of the last frame. `compare` decodes
the record with `recover-real --nes`, takes the grabber's first field
(the console is 240p, so every field is the whole picture), finds the
grabber's horizontal window and vertical offset by luma correlation,
and reports the mean absolute difference, the agreement of flat blocks
(where chroma filtering at edges cannot count), the hue difference on
saturated pixels, and the ten flat blocks that disagree most, by
console coordinates. It writes `captures/<name>-compare.png` (decoder,
grabber, difference) and `.json`. `captures/` is ignored by git.

## What the first synchronized pair said (MEASURED 2026-09-12, `sync1`)

Super Mario Bros. world 1-1, the console idle. The decoder recovered
the record at a rate error of -3.5 ppm with a worst burst residual of
0.17 grid samples. The grabber's console pixel 0 sits at sample 44 of
its 720, four rows lower than the decoder's frame (correlations 0.95
horizontally, 0.996 vertically: the alignment is not in doubt).

| | value |
|---|---|
| flat blocks agreeing, of 240 | 159 flat, mean abs difference 7.6 of 255 |
| hue, grabber minus decoder, on 55,733 saturated pixels | median +2.0 degrees |
| saturation, grabber over decoder | 1.05 |
| whole picture, mean abs difference R, G, B | 18.9, 14.2, 7.7 |

The worst flat blocks are all the sky: the decoder reads it as
(137, 125, 255) and the grabber as (121, 114, 255). Blue is clipped in
both, and the grabber sits about 15 lower in red and green, which is a
black level or contrast difference in the Roxio's chip, uniform across
the picture, not a hue error. Hue agrees to two degrees and saturation
to five percent, which is the number the N6 work cared about: the
decoder's hue is not the odd one out.

The whole-picture difference is edges: the grabber's chroma is 4:2:2
and its filter is not the decoder's, so every vertical edge carries a
halo in the difference image. That is why flat blocks are the figure to
read, and why a running game is the wrong subject: a second's motion
between the two captures looks exactly like a decoding disagreement.

What this is for: the grabber is a second opinion on the same signal.
Where the two agree, both are probably right. Where they differ on a
flat colour, the JSON names the colour and the block, and the question
goes to the console with a probe rather than to either decoder.
