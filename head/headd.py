#!/usr/bin/env python3
"""The head: the bench under one script, on the Raspberry Pi.

  python3 head/headd.py --bridge /dev/ttyUSB0 --scope <ip> [--port 6530] [--runs runs]
  python3 head/headd.py --bridge <pty from tools/fake-bridge.py> --no-gpio --no-scope

One process, three sides. The workstation side is UDP: a JSON request
per datagram, a JSON reply per datagram (`tools/bench.py` is the
client). The bridge side is the firmware's line protocol over serial,
every line it prints appended to the run's `bridge.log`. The bench
side is the Pi's own pins for the reset and power relays and SCPI over
the LAN to the scope, in the dialect ntsc-crt's `scope-capture.py`
proved on the same instrument.

A run is one script (docs/script.md), played line by line into a
directory `runs/<stamp>/`: `script.txt` as received, `bridge.log`,
`head.log` (each line as it was played, with the wall time), and any
captures as `<name>.u8` beside `<name>.toml` in the format ntsc-crt's
recovery ingests. The client fetches the directory over the head's own
HTTP listing on the port after the UDP one.

Requests: {"op": "status"}, {"op": "run", "script": "..."} (starts a
run; refused while one plays), {"op": "abort"}, {"op": "bridge",
"line": "STATUS"} (one line straight to the bridge, its replies within
half a second returned), {"op": "runs"} (the run directories).

Addresses come from the command line or bench.local.md, never from a
file that is committed. The scope belongs to another experiment when
this is not running: its setup is saved before the first command that
changes it and restored after every capture, exactly as scope-capture
does. Nothing here has met the part; the fake bridge and --no-gpio /
--no-scope are what it has run against.
"""
import argparse
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

try:
    import serial
except ImportError:  # the fake bridge's pty works through os as well
    serial = None

RESET_HOLD_S = 0.1
PCNT_LIMIT = None  # the firmware's business; the head only reads its lines


# ----------------------------------------------------------------- bridge
class Bridge:
    """The firmware over its serial line: lines out, lines in, a log."""

    def __init__(self, path, baud=921600):
        self.path = path
        if serial is not None and not path.startswith("/dev/pts/"):
            self.ser = serial.Serial(path, baud, timeout=0.05)
            self.read = self.ser.read
            self.write = self.ser.write
        else:
            # A pty (the fake bridge): plain file descriptors.
            import tty
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            tty.setraw(self.fd)
            self.read = self._read_fd
            self.write = self._write_fd
        self.buf = b""
        self.lines = []          # every line, in order (the run drains it)
        self.latest_latch = -1   # the last L line's index
        self.lock = threading.Lock()
        self.stop = False
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _write_fd(self, b):
        while b:
            try:
                n = os.write(self.fd, b)
                b = b[n:]
            except BlockingIOError:
                time.sleep(0.002)

    def _read_fd(self, n):
        try:
            return os.read(self.fd, n)
        except BlockingIOError:
            return b""

    def _pump(self):
        # Lines nobody drains (no run playing) are kept only up to a
        # bound, so an idle head does not grow without limit.
        while not self.stop:
            data = self.read(4096)
            if not data:
                time.sleep(0.005)
                continue
            self.buf += data
            while b"\n" in self.buf:
                raw, self.buf = self.buf.split(b"\n", 1)
                line = raw.decode(errors="replace").rstrip("\r")
                with self.lock:
                    self.lines.append(line)
                    if len(self.lines) > 100_000:
                        del self.lines[:50_000]
                    if line.startswith("L "):
                        f = line.split()
                        if len(f) == 4:
                            self.latest_latch = int(f[1])

    def send(self, line):
        self.write((line + "\n").encode())

    def drain(self):
        with self.lock:
            out, self.lines = self.lines, []
        return out

    def ask(self, line, wait=0.5):
        """One line to the bridge and the comment lines it answers within
        the wait; the L stream goes on into whatever run is playing."""
        self.send(line)
        time.sleep(wait)
        with self.lock:
            answers = [l for l in self.lines if l.startswith("#")]
            self.lines = [l for l in self.lines if not l.startswith("#")]
        return answers[-20:]


# ------------------------------------------------------------------ relays
class Relays:
    """The reset optocoupler and the power relay on the Pi's pins, or a
    printed stand-in with --no-gpio. Pins per docs/wiring.md."""

    def __init__(self, reset_pin, power_pin, real):
        self.real = real
        self.reset_pin, self.power_pin = reset_pin, power_pin
        self.power_on = None
        if real:
            from gpiozero import DigitalOutputDevice  # Raspberry Pi OS ships it
            self.reset = DigitalOutputDevice(reset_pin, initial_value=False)
            self.power = DigitalOutputDevice(power_pin, initial_value=False)

    def pulse_reset(self, hold=RESET_HOLD_S):
        if self.real:
            self.reset.on()
            time.sleep(hold)
            self.reset.off()
        else:
            time.sleep(hold)
        return f"reset held {hold * 1000:.0f} ms on GPIO{self.reset_pin}" + ("" if self.real else " (no gpio)")

    def set_power(self, on):
        self.power_on = on
        if self.real:
            (self.power.on if on else self.power.off)()
        return f"power {'on' if on else 'off'} on GPIO{self.power_pin}" + ("" if self.real else " (no gpio)")


# ------------------------------------------------------------------- scope
class Scope:
    """The DS1000Z over its raw socket, the dialect of scope-capture.py."""

    PORT = 5555
    CHUNK = 250_000

    def __init__(self, host):
        self.host = host
        self.s = socket.create_connection((host, self.PORT), timeout=5)
        self.s.settimeout(15)
        self.idn = self.ask("*IDN?")
        self.setup = None

    def cmd(self, c):
        self.s.sendall(c.encode() + b"\n")

    def ask(self, c):
        self.cmd(c)
        out = b""
        while not out.endswith(b"\n"):
            out += self.s.recv(4096)
        return out.decode().strip()

    def ask_block(self, c):
        self.cmd(c)
        buf = b""
        while len(buf) < 11:
            buf += self.s.recv(4096)
        assert buf[0:1] == b"#", f"not a TMC block: {buf[:16]!r}"
        ndig = int(buf[1:2])
        length = int(buf[2 : 2 + ndig])
        need = 2 + ndig + length + 1
        while len(buf) < need:
            buf += self.s.recv(65536)
        return buf[2 + ndig : 2 + ndig + length]

    def save_setup(self):
        if self.setup is None:
            self.setup = self.ask_block(":SYSTem:SETup?")
        return len(self.setup)

    def restore_setup(self):
        if self.setup is not None:
            self.s.sendall(b":SYSTem:SETup " + f"#9{len(self.setup):09d}".encode() + self.setup + b"\n")
            time.sleep(2.0)
            self.cmd(":RUN")

    def arm(self, ch, scale, offset, tb=0.005, depth=12_000_000):
        """Single-shot on the external trigger: the next rising edge on
        EXT TRIG stops the scope with the window around it. The
        horizontal offset is set to four divisions so the trigger sits
        early in the record and two full frames follow it, which the
        recovery needs; the sign convention is not trusted: the record's
        preamble says where the trigger fell, and that is what is
        written beside the capture (`trigger_sample`). If the first real
        capture reports the trigger late in the record, flip the sign
        here."""
        self.save_setup()
        off = [f":CHANnel{c}:DISPlay OFF" for c in (1, 2, 3, 4) if c != ch]
        for c in [":STOP", *off, f":CHANnel{ch}:DISPlay ON", f":CHANnel{ch}:PROBe 1", f":CHANnel{ch}:COUPling DC",
                  f":CHANnel{ch}:BWLimit OFF", f":CHANnel{ch}:SCALe {scale}", f":CHANnel{ch}:OFFSet {offset}",
                  ":ACQuire:TYPE NORMal", f":TIMebase:MAIN:SCALe {tb}", f":TIMebase:MAIN:OFFSet {tb * 4}", ":TRIGger:MODE EDGE",
                  ":TRIGger:EDGe:SOURce EXT", ":TRIGger:EDGe:SLOPe POSitive", ":TRIGger:EDGe:LEVel 1.5",
                  ":TRIGger:SWEep SINGle"]:
            self.cmd(c)
            time.sleep(0.08)
        # Memory depth only takes while running (found on the first real capture).
        self.cmd(":RUN")
        time.sleep(0.5)
        self.cmd(f":ACQuire:MDEPth {depth}")
        time.sleep(0.5)
        got = self.ask(":ACQuire:MDEPth?")
        if got.strip() != str(depth):
            raise RuntimeError(f"memory depth did not take: {got!r}")
        self.cmd(":SINGle")
        time.sleep(0.3)
        return self.ask(":TRIGger:STATus?")

    def triggered(self):
        return self.ask(":TRIGger:STATus?").strip() == "STOP"

    def read_record(self, ch, out_dir, name, note):
        srate = float(self.ask(":ACQuire:SRATe?"))
        mdepth = int(float(self.ask(":ACQuire:MDEPth?")))
        self.cmd(f":WAVeform:SOURce CHANnel{ch}")
        self.cmd(":WAVeform:MODE RAW")
        self.cmd(":WAVeform:FORMat BYTE")
        data = bytearray()
        for start in range(1, mdepth + 1, self.CHUNK):
            stop = min(start + self.CHUNK - 1, mdepth)
            self.cmd(f":WAVeform:STARt {start}")
            self.cmd(f":WAVeform:STOP {stop}")
            data += self.ask_block(":WAVeform:DATA?")
        if len(data) != mdepth:
            raise RuntimeError(f"short read: {len(data)} of {mdepth}")
        # The preamble's xorigin is the first sample's time relative to
        # the trigger (negative when the trigger is inside the record),
        # xincrement the sample period: the trigger's sample index
        # follows without any offset sign convention.
        pre = self.ask(":WAVeform:PREamble?").split(",")
        xinc, xorig = float(pre[4]), float(pre[5])
        trigger_sample = int(round(-xorig / xinc))
        (out_dir / f"{name}.u8").write_bytes(bytes(data))
        (out_dir / f"{name}.toml").write_text(
            f'file = "{name}.u8"\nformat = "u8"\nrate_hz = {srate:.1f}\ntrigger_sample = {trigger_sample}\n'
            f'# captured {time.strftime("%Y-%m-%d %H:%M")} from {self.idn.split(",")[1] if "," in self.idn else self.idn}\n'
            f"# by nes-bench head: CH{ch}, EXT TRIG single-shot, xorigin {xorig:g} s; {note}\n"
        )
        lo, hi = min(data), max(data)
        return dict(points=mdepth, rate=srate, lo=lo, hi=hi, trigger_sample=trigger_sample)


# -------------------------------------------------------------------- runs
class Run(threading.Thread):
    """One script, played line by line on its own thread."""

    def __init__(self, head, script):
        super().__init__(daemon=True)
        self.head = head
        self.script = script
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = head.runs / self.stamp
        self.dir.mkdir(parents=True)
        (self.dir / "script.txt").write_text(script)
        self.log = open(self.dir / "head.log", "w")
        self.blog = open(self.dir / "bridge.log", "w")
        self.abort = False
        self.state = "starting"
        self.line_no = 0
        self.error = None
        self.armed = None  # (name, ch, note) while a capture waits for its trigger
        head.bridge.drain()  # the log is this run's lines, not the idle backlog

    def say(self, s):
        self.log.write(f"{time.time():.3f} {s}\n")
        self.log.flush()
        self.state = s

    def pump_bridge(self):
        for line in self.head.bridge.drain():
            self.blog.write(line + "\n")
        self.blog.flush()

    def run(self):
        try:
            for raw in self.script.splitlines():
                self.line_no += 1
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                if self.abort:
                    self.say("aborted")
                    return
                self.play(line)
                self.pump_bridge()
            if self.armed:
                self.wait_capture()
            self.say("done")
        except Exception as e:  # noqa: BLE001 - the run's own record is the point
            self.error = f"line {self.line_no}: {e}"
            self.say(f"failed: {self.error}")
        finally:
            self.pump_bridge()
            self.log.close()
            self.blog.close()
            self.head.current = None

    def play(self, line):
        h = self.head
        w = line.split()
        op = w[0].upper()
        if op in ("MODE", "SET", "AT", "TRIG"):
            h.bridge.send(line.upper() if op == "MODE" else line)
            self.say(f"bridge <- {line}")
        elif op == "RESET":
            h.bridge.send("RESET")
            self.say("bridge <- RESET; " + h.relays.pulse_reset())
        elif op == "POWER":
            on = w[1].upper() == "ON"
            self.say(h.relays.set_power(on))
        elif op == "WAIT":
            # WAIT n: until the bridge has reported latch n; WAIT n S: seconds.
            if len(w) == 3 and w[2].upper() == "S":
                self.say(f"wait {w[1]} s")
                t = time.time() + float(w[1])
                while time.time() < t and not self.abort:
                    time.sleep(0.05)
                    self.pump_bridge()
            else:
                n = int(w[1])
                self.say(f"wait for latch {n}")
                while h.bridge.latest_latch < n and not self.abort:
                    time.sleep(0.02)
                    self.pump_bridge()
                    if self.armed and h.scope and h.scope.triggered():
                        self.finish_capture()
        elif op == "ARM":
            # ARM name [channel] [scale] [offset]
            name = w[1]
            ch = int(w[2]) if len(w) > 2 else 3
            scale = float(w[3]) if len(w) > 3 else 0.5
            offset = float(w[4]) if len(w) > 4 else -1.3
            if h.scope is None:
                self.say(f"arm {name}: no scope (--no-scope); recorded as not captured")
                return
            status = h.scope.arm(ch, scale, offset)
            self.armed = (name, ch, f"{scale * 1000:.0f} mV/div, {offset * 1000:.0f} mV offset")
            self.say(f"armed {name} on CH{ch}, trigger status {status}")
        elif op == "CAPTURE":
            # CAPTURE: wait for the armed trigger, read the record.
            if not self.armed:
                raise ValueError("CAPTURE with nothing armed")
            self.wait_capture()
        else:
            raise ValueError(f"unknown word {op}")

    def wait_capture(self):
        h = self.head
        t0 = time.time()
        while not h.scope.triggered() and not self.abort:
            if time.time() - t0 > 60:
                raise TimeoutError("the scope did not trigger within a minute")
            time.sleep(0.1)
            self.pump_bridge()
        self.finish_capture()

    def finish_capture(self):
        h = self.head
        name, ch, note = self.armed
        self.armed = None
        self.say(f"reading {name}")
        info = h.scope.read_record(ch, self.dir, name, note)
        self.say(f"captured {name}: {info['points']} points at {info['rate']:.0f} Sa/s, range {info['lo']}..{info['hi']}, trigger at sample {info['trigger_sample']}")
        h.scope.restore_setup()


# -------------------------------------------------------------------- head
class Head:
    def __init__(self, a):
        self.runs = Path(a.runs)
        self.runs.mkdir(exist_ok=True)
        self.bridge = Bridge(a.bridge, a.baud)
        self.relays = Relays(a.reset_pin, a.power_pin, real=not a.no_gpio)
        self.scope = None if a.no_scope else Scope(a.scope)
        self.current = None
        self.started = time.time()

    def handle(self, req):
        op = req.get("op")
        if op == "status":
            cur = self.current
            return dict(ok=True, up=round(time.time() - self.started, 1), bridge=self.bridge.path, latest_latch=self.bridge.latest_latch,
                        scope=self.scope.idn if self.scope else None, gpio=self.relays.real, power=self.relays.power_on,
                        run=None if cur is None else dict(stamp=cur.stamp, state=cur.state, line=cur.line_no, error=cur.error))
        if op == "run":
            if self.current is not None:
                return dict(ok=False, error="a run is playing", stamp=self.current.stamp)
            r = Run(self, req.get("script", ""))
            self.current = r
            r.start()
            return dict(ok=True, stamp=r.stamp)
        if op == "abort":
            if self.current is None:
                return dict(ok=False, error="nothing playing")
            self.current.abort = True
            return dict(ok=True, stamp=self.current.stamp)
        if op == "bridge":
            return dict(ok=True, lines=self.bridge.ask(req.get("line", "STATUS")))
        if op == "runs":
            return dict(ok=True, runs=sorted(p.name for p in self.runs.iterdir() if p.is_dir()))
        return dict(ok=False, error=f"unknown op {op!r}")


def serve_udp(head, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    while True:
        data, addr = s.recvfrom(65535)
        try:
            req = json.loads(data.decode())
            rep = head.handle(req)
        except Exception as e:  # noqa: BLE001
            rep = dict(ok=False, error=str(e))
        out = json.dumps(rep).encode()
        if len(out) > 60_000:
            out = json.dumps(dict(ok=False, error=f"reply of {len(out)} bytes does not fit a datagram")).encode()
        s.sendto(out, addr)


def serve_http(root, port):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(root), **k)  # noqa: E731
    with socketserver.ThreadingTCPServer(("0.0.0.0", port), handler) as httpd:
        httpd.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", required=True, help="the ESP32's serial device, or a pty from tools/fake-bridge.py")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--scope", default=None, help="the DS1000Z's address on the LAN")
    ap.add_argument("--no-scope", action="store_true")
    ap.add_argument("--no-gpio", action="store_true", help="print the relay actions instead of driving pins")
    ap.add_argument("--reset-pin", type=int, default=17)
    ap.add_argument("--power-pin", type=int, default=27)
    ap.add_argument("--port", type=int, default=6530, help="UDP for requests; HTTP for the runs on port+1")
    ap.add_argument("--runs", default="runs")
    a = ap.parse_args()
    if not a.no_scope and not a.scope:
        ap.error("--scope <ip> or --no-scope")
    head = Head(a)
    threading.Thread(target=serve_http, args=(head.runs, a.port + 1), daemon=True).start()
    print(f"headd: bridge {a.bridge}, scope {head.scope.idn if head.scope else 'none'}, gpio {'on' if not a.no_gpio else 'off'}; UDP {a.port}, HTTP {a.port + 1}, runs in {head.runs}", flush=True)
    serve_udp(head, a.port)


if __name__ == "__main__":
    sys.exit(main())
