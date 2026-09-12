# Plan: the reader's card on the Pi

Written 2026-09-12, before anything is built. The cart reader (OSCR
V15.6, on the Pi's `/dev/ttyUSB0`) keeps its screen and dial, and its
serial channel is the updater only: no command starts a dump or reads
a file. Everything the reader knows arrives on its SD card and
everything it produces leaves on it. Today that means the card
travelling to a PC for the database refresh and for every dump. The
plan is to give the Pi a USB card reader, so the card moves ten
centimetres instead: reader off, card out, into the Pi's reader, and
the workstation does the rest over ssh.

## What it buys

- The database refresh (`~/oscr-sd-V15.6/` on the Pi, 45 files) goes
  on from here, with the line counts checked before and after.
- A dump comes off as soon as it is made, is CRC-checked against the
  same `nes.txt` the reader uses, and is banked on the workstation's
  ROM store, which is never a repository (`roms/` and `*.nes` are
  ignored here).
- A dumped ROM is what the model needs to render the same screen the
  console is showing, which turns the eyes-versus-scope comparison into
  a three-way one: the decoder's picture, the grabber's, and the
  model's, all of the same title.

## The hook: a label on the card

While the card is being prepped, give it the volume label `OSCR`
(FAT32; on Linux `sudo fatlabel /dev/sdX1 OSCR`, on Windows or a Mac
rename the volume). That label is what the Pi will key on, so any
other card in the reader is left alone. If the card is prepped without
it, the Pi can label it later, unmounted, with the same command.

## The mount

`udisks2` is installed on the Pi but inactive, as it is on a box with
no desktop session, so automounting is written down rather than hoped
for: one udev rule in `/etc/udev/rules.d/99-oscr-card.rules` matching
`ENV{ID_FS_LABEL}=="OSCR"` that runs `systemd-mount --no-block
--collect -o uid=1000,gid=1000,umask=022,flush` to `/mnt/oscr`, and
unmounts on removal. `flush` so a copy is on the card when the command
returns, uid so the tool needs no root. Nothing else on the Pi touches
`/mnt/oscr`.

## The tool: `tools/oscr-card.py`

Run from the workstation, works through ssh to the Pi, and refuses
before it does anything the card cannot undo.

- `status`: is the card in, its label, free space, the database files
  with their line counts, and every numbered dump folder with what is
  in it.
- `refresh`: copies the 45 staged files into the card's root,
  overwriting, then reads each back and compares bytes; prints the
  database line counts before and after (`nes.txt` 9,330 to 22,143 is
  the one to see). Refuses if the staged set is not exactly 45 files,
  and never writes into a numbered folder.
- `pull`: copies every numbered folder the workstation does not yet
  have to `/mnt/tm/nes-dumps/<date>-<folder>/`, checks each file's
  bytes after the copy, computes the CRC32 of each `.nes` the way the
  reader does and looks it up in the staged `nes.txt`, and writes a
  manifest beside the files naming what the database calls it. A dump
  whose CRC the database does not know is kept and said so; it is not
  an error, it is what the reader's "hash not found" looks like from
  this side. Never deletes anything on the card.
- `eject`: sync, unmount, and say when the card can come out.

Every refusal is a test: `MUTATE=1` drops one file from the staged set
and `refresh` must refuse; `MUTATE_PULL=1` corrupts a byte after the
copy and `pull` must refuse. A tool that has never been seen to refuse
has not been checked.

## Rules, stated once

- Never format the card and never delete on it. The numbered folders
  are the user's dumps.
- Refuse a card without the `OSCR` label, and refuse a card with the
  label but no `nes.txt` at its root: that is the wrong card or a
  broken one, and the tool should say which.
- ROMs never enter a repository. The dump store is `/mnt/tm/nes-dumps`
  on the workstation, beside the scope captures already banked there.

## Done so far (2026-09-12)

Steps 1 to 3, and the refresh of step 5: the card is labelled `OSCR`, a
Genesys microSD reader is on the Pi, the udev rule is installed and
exercised both ways, and the 45 files are on the card, read back
identical. `tools/oscr-card.py` is not written yet; the refresh was done
by hand with the checks the tool will carry.

## The order

1. The card gets its label during the prep that is happening now.
2. Any USB card reader on the Pi. Plug it in with the card; `lsblk` on
   the Pi should show it with the label.
3. The udev rule, tested by pulling and re-inserting the card: mounted
   at `/mnt/oscr`, gone on removal.
4. The tool, with its refusals proven before its copies are trusted.
5. First `refresh`, then the reader finds this cartridge's hash by
   itself; first `pull`, the Super Mario Bros. and Duck Hunt dump, CRC
   `D26EFD78` if the database is right about it, banked and named.
6. Then the three-way comparison: the model on the dumped ROM beside
   the decoder and the grabber.
