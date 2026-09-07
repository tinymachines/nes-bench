#!/usr/bin/env python3
"""A DS1000Z that is not there: the SCPI subset the head speaks, on a
TCP port, answering the waveform reads with synthesised records so the
head's arm, capture and read path runs on a box with no scope.

  python3 tools/fake-scope.py [--port 5555] [--cpu 4 --ppu 3]
  python3 tools/fake-scope.py --video rom.nes --runs <the head's runs dir> --trigger-file <the fake bridge's> [--diverge-at N hh]

The records: channels 1, 2 and 4 carry the master clock, M2 and ALE
for the given alignment (tools/b2-align.py's synthesis, the measured
pin offsets), other channels a flat line. With --video, channel 3
carries the model's own synthesis of the ROM at the latch the fake
bridge last triggered at, under the newest script in the head's runs
directory (nes-console's capture-score with SYNTH_OUT), and
--diverge-at N hh appends `AT N hh` to that script so the "part" plays
a different byte from latch N on: what B3's bisection has to find. The
trigger is reported at the sample the synthesis names. It is a stand-in
for the protocol only: nothing about the instrument's timing is in it.
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


def video_record(a, n):
    """The model's synthesis at the fake bridge's trigger latch, as the
    record the head will read: (samples, trigger_sample)."""
    import subprocess
    import tempfile
    latch = int(Path(a.trigger_file).read_text().strip())
    runs = sorted(p for p in Path(a.runs).iterdir() if p.is_dir())
    script = (runs[-1] / "script.txt").read_text() if runs else ""
    if a.diverge_at:
        script += f"\nAT {a.diverge_at[0]} {a.diverge_at[1]}\n"
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "script.txt"
        sp.write_text(script)
        out = Path(d) / "synth.u8"
        env = dict(SCRIPT=str(sp), LATCH=str(latch), SYNTH_TRIGGER="1", SYNTH_OUT=str(out), PATH=__import__("os").environ["PATH"], HOME=__import__("os").environ["HOME"])
        r = subprocess.run(["cargo", "run", "--release", "-p", "nes-console", "--example", "capture-score", "--", a.video, "4000"],
                           cwd=a.nes, env=env, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"capture-score failed at latch {latch}: {r.stdout[-600:]}{r.stderr[-600:]}")
        data = np.fromfile(out, dtype=np.uint8)
        trig = int(__import__("re").search(r"trigger_sample = (\d+)", (Path(d) / "synth.u8.toml").read_text()).group(1))
    print(f"fake scope: video at latch {latch}: {len(data)} samples, trigger at {trig}" + (f", diverged from {a.diverge_at[0]}" if a.diverge_at else ""), flush=True)
    if len(data) < n:
        data = np.concatenate([data, np.full(n - len(data), data[-1], dtype=np.uint8)])
    return data[:n], trig


def serve(conn, a):
    state = {"run": False, "single": False, "mdepth": 12000000, "src": 1, "start": 1, "stop": 1}
    rate = 250e6
    if a.video:
        state["rate"] = 125e6  # the synthesis is at the scope's one-channel rate
    records = {}
    buf = b""

    def block(payload):
        return b"#9" + f"{len(payload):09d}".encode() + payload + b"\n"

    lock = threading.Lock()

    def record(ch):
        with lock:
            return record_locked(ch)

    def record_locked(ch):
        if ch not in records:
            n = state["mdepth"]
            if a.video and ch == 3:
                data, trig = video_record(a, n)
                records[ch] = data
                state["trigger_sample"] = trig
            elif ch in (1, 2, 4):
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
                state["armed_at"] = __import__("time").time()
                with lock:
                    records.pop(3, None)
                state["synth_started"] = False
            elif u.startswith(":ACQUIRE:MDEPTH "):
                if state["run"]:
                    # As the real one: the depth only takes while running.
                    state["mdepth"] = int(u.split()[-1])
                    records.clear()
            elif u == ":ACQUIRE:MDEPTH?":
                conn.sendall(f"{state['mdepth']}\n".encode())
            elif u == ":ACQUIRE:SRATE?":
                conn.sendall(f"{state.get('rate', rate):.0f}\n".encode())
            elif u == ":TRIGGER:STATUS?":
                # Armed single shot: with --video, triggered once the fake
                # bridge has fired its trigger since the arm (its file is
                # newer); otherwise at once (the console is "on").
                fired = state["single"]
                if fired and a.video and a.trigger_file:
                    try:
                        fired = Path(a.trigger_file).stat().st_mtime >= state.get("armed_at", 0)
                    except FileNotFoundError:
                        fired = False
                if fired and a.video and 3 not in records and not state.get("synth_started"):
                    # Start the synthesis now, so the head's read finds it.
                    state["synth_started"] = True
                    threading.Thread(target=record, args=(3,), daemon=True).start()
                conn.sendall(b"STOP\n" if fired else b"RUN\n")
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
                # format,type,points,count,xinc,xorig,xref,yinc,yorig,yref:
                # the trigger a fifth in, or where the video synthesis put it.
                n = state["mdepth"]
                r = state.get("rate", rate)
                trig = state.get("trigger_sample", n / 5)
                conn.sendall(f"0,2,{n},1,{1 / r:.6e},{-trig / r:.6e},0,0.02,0,128\n".encode())
            elif u.endswith("?"):
                conn.sendall(b"0\n")
            # Everything else is a setting the fake accepts silently.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--cpu", type=int, default=4)
    ap.add_argument("--ppu", type=int, default=3)
    ap.add_argument("--video", default=None, help="a ROM: channel 3 carries the model's synthesis at the fake bridge's trigger latch")
    ap.add_argument("--runs", default="runs", help="the head's runs directory (the newest script.txt is the run's)")
    ap.add_argument("--trigger-file", default=None)
    ap.add_argument("--diverge-at", nargs=2, default=None, metavar=("N", "HH"))
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
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
