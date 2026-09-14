#!/usr/bin/env python3
"""An iNES file into the two images a flash chip takes: the header off,
the program and the tiles apart, each tiled end to end to the chip's
size.

  python3 tools/nesprep.py roms/cal.nes [--outdir roms/cal-flash] [--size 524288]
  python3 tools/nesprep.py --selftest roms/cal.nes

The cart (the owner's build spec, 2026-09-14, docs/build-the-cal-cart.md):
an NES CART PCB "discrete mapper board" v3.3 with two 32-pin footprints,
U3 for CHR and U4 for PRG, both SST39SF040 (512 KiB, 5 V parallel
flash), programmed in an XGecu Pro (TL866 family); NROM, so U5 to U7
stay empty and the H/V solder jumper follows the header's mirroring
bit; the console's lockout is defeated, so U2 stays empty too.

Why tile and not zero-fill: the chip has nineteen address lines and an
NROM board drives fifteen of them for PRG and thirteen for CHR; the
rest are not driven, so the chip may be read anywhere in its 512 KiB.
With the image repeated, every combination of the undriven lines lands
on a copy; zero-filled, the cart works only if they happen to read low.
A region whose size does not divide the chip's is refused, as is a
file shorter than its header claims, a header without the magic, and a
CHR size of zero (CHR RAM: a different board configuration), which is
warned about rather than written as an empty image.

--selftest tiles roms/cal.nes and holds every copy to the slice it came
from, the copy counts to the sizes, and prints the sha256 of each image
for the tutorial's table. MUTATE=1 tiles one byte short and must fail.
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

HEADER = 16
TRAINER = 512
MAGIC = b"NES\x1a"


def parse(data: bytes):
    if data[:4] != MAGIC:
        raise ValueError("not an iNES file (the magic bytes are not NES<1A>)")
    prg_len = data[4] * 16 * 1024
    chr_len = data[5] * 8 * 1024
    flags6 = data[6]
    mapper = (flags6 >> 4) | (data[7] & 0xF0)
    mirroring = "vertical" if flags6 & 1 else "horizontal"
    offset = HEADER + (TRAINER if flags6 & 4 else 0)
    if len(data) < offset + prg_len + chr_len:
        raise ValueError(f"the file is {len(data)} bytes; the header claims {offset + prg_len + chr_len}")
    prg = data[offset:offset + prg_len]
    chr_ = data[offset + prg_len:offset + prg_len + chr_len]
    return {"mapper": mapper, "mirroring": mirroring, "trainer": bool(flags6 & 4), "prg": prg, "chr": chr_}


def tile(chunk: bytes, target: int, label: str) -> bytes:
    if not chunk:
        raise ValueError(f"the {label} region is empty")
    if target % len(chunk):
        raise ValueError(f"the {label} region ({len(chunk)} bytes) does not divide the chip ({target} bytes)")
    return chunk * (target // len(chunk))


def prep(rom: Path, outdir: Path, size: int, mutate: bool = False):
    info = parse(rom.read_bytes())
    outdir.mkdir(parents=True, exist_ok=True)
    out = {}
    prg = tile(info["prg"], size, "PRG")
    if mutate:
        prg = prg[:-1]
    (outdir / "prg.bin").write_bytes(prg)
    out["prg.bin"] = (len(info["prg"]), size // len(info["prg"]), hashlib.sha256(prg).hexdigest())
    if len(info["chr"]) == 0:
        print("CHR size is 0: the ROM uses CHR RAM; no chr.bin written (this board would need CHR RAM fitted)")
    else:
        c = tile(info["chr"], size, "CHR")
        (outdir / "chr.bin").write_bytes(c)
        out["chr.bin"] = (len(info["chr"]), size // len(info["chr"]), hashlib.sha256(c).hexdigest())
    print(f"{rom.name}: mapper {info['mapper']}, {info['mirroring']} mirroring{', trainer skipped' if info['trainer'] else ''}")
    for name, (n, k, sha) in out.items():
        print(f"  {name}: {n // 1024} KiB image x{k} = {size} bytes  sha256 {sha}")
    return info, out


def selftest(rom: Path, size: int) -> int:
    mutate = bool(os.environ.get("MUTATE"))
    outdir = rom.parent / (rom.stem + "-flash")
    info, out = prep(rom, outdir, size, mutate=mutate)
    fails = 0
    for name, region in (("prg.bin", info["prg"]), ("chr.bin", info["chr"])):
        if name not in out:
            continue
        img = (outdir / name).read_bytes()
        n = len(region)
        if len(img) != size:
            print(f"  {name}: {len(img)} bytes, not {size}")
            fails += 1
            continue
        bad = [i for i in range(size // n) if img[i * n:(i + 1) * n] != region]
        if bad:
            print(f"  {name}: copies {bad[:5]}{'...' if len(bad) > 5 else ''} differ from the region")
            fails += 1
        else:
            print(f"  {name}: all {size // n} copies are the region, byte for byte")
    if info["mapper"] != 0:
        print(f"  mapper {info['mapper']} is not NROM: this board needs its logic parts for that")
        fails += 1
    print("selftest:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path)
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--size", type=int, default=512 * 1024)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest(a.rom, a.size))
    try:
        prep(a.rom, a.outdir or a.rom.parent / (a.rom.stem + "-flash"), a.size)
    except ValueError as e:
        sys.exit(f"REFUSED: {e}")


if __name__ == "__main__":
    main()
