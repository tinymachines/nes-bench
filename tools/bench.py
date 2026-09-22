#!/usr/bin/env python3
"""The workstation's side of the head: send a script, watch it play,
fetch the run.

  python3 tools/bench.py <head> status
  python3 tools/bench.py <head> run script.txt [--fetch runs/]
  python3 tools/bench.py <head> abort
  python3 tools/bench.py <head> bridge "STATUS"
  python3 tools/bench.py <head> pad            # the gamepads the head can see
  python3 tools/bench.py <head> pad on         # give the console to one
  python3 tools/bench.py <head> pad off
  python3 tools/bench.py <head> runs
  python3 tools/bench.py <head> fetch <stamp> [--into runs/]

<head> is host[:port] (the head's UDP port, default 6530; its HTTP
listing is on the next port). `run` waits until the head reports the
run done or failed, printing the state as it changes, then fetches the
run's directory (script, head.log, bridge.log, captures) into runs/
unless --no-fetch. The head's address is never committed: it lives in
bench.local.md or on the command line.
"""
import argparse
import json
import socket
import sys
import time
import urllib.request
from pathlib import Path


def ask(host, port, req, timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    s.sendto(json.dumps(req).encode(), (host, port))
    data, _ = s.recvfrom(65535)
    return json.loads(data.decode())


def fetch(host, port, stamp, into):
    base = f"http://{host}:{port + 1}/{stamp}/"
    listing = urllib.request.urlopen(base, timeout=10).read().decode()
    names = sorted(set(n for n in __import__("re").findall(r'href="([^"?/]+)"', listing)))
    out = Path(into) / stamp
    out.mkdir(parents=True, exist_ok=True)
    for n in names:
        data = urllib.request.urlopen(base + n, timeout=120).read()
        (out / n).write_bytes(data)
        print(f"  {n}: {len(data)} bytes")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("head")
    ap.add_argument("op", choices=["status", "run", "abort", "bridge", "runs", "fetch", "pad"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--into", default="runs")
    ap.add_argument("--device", help="pad on: the event device, when the head has more than one")
    a = ap.parse_args()
    host, _, port = a.head.partition(":")
    port = int(port) if port else 6530
    if a.op == "status":
        print(json.dumps(ask(host, port, {"op": "status"}), indent=2))
    elif a.op == "runs":
        print("\n".join(ask(host, port, {"op": "runs"}).get("runs", [])))
    elif a.op == "abort":
        print(ask(host, port, {"op": "abort"}))
    elif a.op == "bridge":
        for line in ask(host, port, {"op": "bridge", "line": a.arg or "STATUS"}).get("lines", []):
            print(line)
    elif a.op == "fetch":
        print(fetch(host, port, a.arg, a.into))
    elif a.op == "pad":
        # `pad` with no argument lists what the head's Bluetooth has; `on`
        # gives the console to it until `off`. The session is a run
        # directory like any other, so `runs` and `fetch` reach it and
        # b3.py builds a replay from its bridge.log.
        action = a.arg or "status"
        rep = ask(host, port, {"op": "pad", "action": action, **({"device": a.device} if a.device else {})})
        if not rep.get("ok"):
            print(rep.get("error", rep))
            return 1
        if action == "status":
            for d in rep.get("pads", []):
                print(f"{d['device']}  {d['name']}")
            if not rep.get("pads"):
                print("no gamepad on the head: pair one with bluetoothctl there")
            print(f"a hand is {'playing' if rep.get('playing') else 'not playing'}")
        else:
            print(rep)
    elif a.op == "run":
        script = Path(a.arg).read_text()
        rep = ask(host, port, {"op": "run", "script": script})
        if not rep.get("ok"):
            print(rep)
            return 1
        stamp = rep["stamp"]
        print(f"run {stamp}")
        last = None
        quiet = 0
        while True:
            # The head answers nothing for about a minute while it reads a
            # 12 M point record off the scope (the first E2 run, 2026-09-18:
            # the client died at "reading" with the capture half fetched).
            try:
                st = ask(host, port, {"op": "status"})
            except socket.timeout:
                quiet += 1
                if quiet > 120:
                    raise
                continue
            quiet = 0
            run = st.get("run")
            if run is None:
                break
            if run["state"] != last:
                print(f"  [{run['line']}] {run['state']}")
                last = run["state"]
            time.sleep(0.25)
        if not a.no_fetch:
            out = fetch(host, port, stamp, a.into)
            head_log = (out / "head.log").read_text().strip().splitlines()
            print(head_log[-1] if head_log else "(no head.log)")
            return 0 if head_log and head_log[-1].endswith(" done") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
