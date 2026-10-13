#!/usr/bin/env python3
"""Pair, trust and connect a BLE device from a Linux host with bluetoothctl,
driven through a pseudo-terminal so its yes/no prompt gets answered.

  python3 tools/btpair.py B0:A6:04:8A:D7:0E          # pair, trust, connect, report
  python3 tools/btpair.py B0:A6:04:8A:D7:0E --remove # forget it here first

WHY A PSEUDO-TERMINAL. bluetoothctl reads its "[agent] Accept pairing
(yes/no):" prompt from a terminal, not from stdin: piped answers are
lost, bluetoothd logs "No agent available for request type 2", and the
pairing fails with AuthenticationFailed while looking like a radio
problem. MEASURED 2026-10-13 on the bench Pi (BlueZ 5.66), three
piped attempts in a row. This runs bluetoothctl in a pty, registers a
NoInputNoOutput agent, trusts the address before pairing (so BlueZ can
accept a just-works pairing itself), and answers any prompt it still
raises with yes. Nothing here needs root or python packages.

The other half of a pairing lives on the device: a pad that stored a
bond from a failed attempt refuses the next one, and says nothing.
firmware/pad's FORGET clears its side; --remove clears this side.
"""
import os
import pty
import re
import select
import sys
import time

ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


def main():
    if len(sys.argv) < 2 or not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", sys.argv[1]):
        sys.exit("usage: btpair.py XX:XX:XX:XX:XX:XX [--remove]")
    mac = sys.argv[1].upper()
    remove = "--remove" in sys.argv
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("bluetoothctl", ["bluetoothctl"])

    def send(s):
        os.write(fd, s.encode() + b"\n")

    def pump(secs):
        """Read for `secs`, answer prompts, return the clean text."""
        end = time.time() + secs
        out = b""
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            try:
                b = os.read(fd, 4096)
            except OSError:
                break
            out += b
            if b"(yes/no)" in b:
                os.write(fd, b"yes\n")
                print("  (prompt answered yes)", flush=True)
        return ANSI.sub(b"", out).replace(b"\r", b"").decode("utf-8", "replace")

    pump(2)
    send("agent NoInputNoOutput"); pump(1)
    send("default-agent"); pump(1)
    send("pairable on"); pump(1)
    if remove:
        send(f"remove {mac}"); print(pump(2).strip().splitlines()[-1])
    send("scan on"); pump(8)
    send(f"trust {mac}"); pump(2)
    send(f"pair {mac}")
    text = pump(20)
    for line in text.splitlines():
        if re.search(r"Pairing successful|Failed to pair|AuthenticationFailed", line):
            print(line.strip())
    send(f"connect {mac}"); pump(8)
    send(f"info {mac}")
    info = pump(3)
    send("quit"); pump(1)
    state = {k: v for k, v in re.findall(r"(Paired|Bonded|Trusted|Connected): (yes|no)", info)}
    print(" ".join(f"{k} {v}" for k, v in state.items()) or "no info came back")
    return 0 if state.get("Paired") == "yes" and state.get("Connected") == "yes" else 1


if __name__ == "__main__":
    sys.exit(main())
