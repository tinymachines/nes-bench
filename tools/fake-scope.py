#!/usr/bin/env python3
"""A DS1000Z that is not there: the SCPI subset the head speaks, on a
TCP port, answering the waveform reads with synthesised records so the
head's arm, capture and read path runs on a box with no scope.

  python3 tools/fake-scope.py [--port 5555] [--cpu 4 --ppu 3]

The records: channels 1, 2 and 4 carry the master clock, M2 and ALE
for the given alignment (tools/b2-align.py's synthesis, the measured
pin offsets), other channels a flat line. The trigger is reported at a
fixed sample so the preamble path is exercised. It is a stand-in for
the protocol only: nothing about the instrument's timing is in it.
"""
import argparse
import socket
import sys
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module  # noqa: E402

align = import_module("b2-align")


def serve(conn, a):
    state = {"run": False, "single": False, "mdepth": 12000000, "src": 1, "start": 1, "stop": 1}
    rate = 250e6
    records = {}
    buf = b""

    def block(payload):
        return b"#9" + f"{len(payload):09d}".encode() + payload + b"\n"

    def record(ch):
        if ch not in records:
            n = state["mdepth"]
            if ch in (1, 2, 4):
                m, m2, ale = align.synthesise(a.cpu, a.ppu, rate, seconds=n / rate)
                records[ch] = {1: m, 2: m2, 4: ale}[ch]
            else:
                records[ch] = np.full(n, 128, dtype=np.uint8)
        return records[ch]

    while True:
        data = conn.recv(65536)
        if not data:
            return
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            c = line.decode(errors="replace").strip()
            u = c.upper()
            if u == "*IDN?":
                conn.sendall(b"RIGOL TECHNOLOGIES,DS1054Z,FAKE0000000000,00.04.04.SP4\n")
            elif u == ":SYSTEM:SETUP?" or u == ":SYSTEM:SETUP?":
                conn.sendall(block(b"\x00" * 1024))
            elif u.startswith(":SYSTEM:SETUP ") or u.startswith(":SYSTEM:SETUP #"):
                pass
            elif u == ":RUN":
                state["run"] = True
            elif u == ":STOP":
                state["run"] = False
            elif u == ":SINGLE":
                state["single"] = True
                state["run"] = True
            elif u.startswith(":ACQUIRE:MDEPTH "):
                if state["run"]:
                    # As the real one: the depth only takes while running.
                    state["mdepth"] = int(u.split()[-1])
                    records.clear()
            elif u == ":ACQUIRE:MDEPTH?":
                conn.sendall(f"{state['mdepth']}\n".encode())
            elif u == ":ACQUIRE:SRATE?":
                conn.sendall(f"{rate:.0f}\n".encode())
            elif u == ":TRIGGER:STATUS?":
                # Armed single shot: triggered at once (the console is "on").
                conn.sendall(b"STOP\n" if state["single"] else b"RUN\n")
            elif u.startswith(":WAVEFORM:SOURCE "):
                state["src"] = int(u.rsplit("CHANNEL", 1)[-1])
            elif u.startswith(":WAVEFORM:START "):
                state["start"] = int(u.split()[-1])
            elif u.startswith(":WAVEFORM:STOP "):
                state["stop"] = int(u.split()[-1])
            elif u == ":WAVEFORM:DATA?":
                r = record(state["src"])
                conn.sendall(block(r[state["start"] - 1 : state["stop"]].tobytes()))
            elif u == ":WAVEFORM:PREAMBLE?":
                # format,type,points,count,xinc,xorig,xref,yinc,yorig,yref: the trigger a fifth in.
                n = state["mdepth"]
                conn.sendall(f"0,2,{n},1,{1 / rate:.6e},{-(n / 5) / rate:.6e},0,0.02,0,128\n".encode())
            elif u.endswith("?"):
                conn.sendall(b"0\n")
            # Everything else is a setting the fake accepts silently.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--cpu", type=int, default=4)
    ap.add_argument("--ppu", type=int, default=3)
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", a.port))
    s.listen(4)
    print(f"fake scope on 127.0.0.1:{a.port}: alignment cpu_phase {a.cpu} ppu_phase {a.ppu}; the protocol only", flush=True)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=serve, args=(conn, a), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
