#!/usr/bin/env python3
"""Bench bring-up: the v1b bridge built one step at a time, with a check
at the end of each and a lab notebook written as it goes.

  python3 tools/bringup.py                 # run from where you left off
  python3 tools/bringup.py --list          # the steps and their state
  python3 tools/bringup.py --step 3.2      # one step, again
  python3 tools/bringup.py --from 2.1      # from there on
  python3 tools/bringup.py --no-scope      # instrument absent: its steps SKIP
  python3 tools/bringup.py --bridge /dev/ttyACM0     # or a fake-bridge pty

Every step prints what to do, waits for you, then checks something. A
check either measures with an instrument or asks you for a number; it
never just asks whether it worked. A step that fails stops the run,
because the next step assumes the last one, and a bridge built on an
unverified pinout is how an ESP32 dies.

What it writes is `docs/lab-log.jsonl`, one JSON object per attempt,
append-only: the step, the time, what was measured, whether it held, and
the photographs it asked for. `tools/lab-notebook.py` renders that into
`docs/lab-notebook.md`, so the notebook is derived from the log and not
typed, and re-rendering after the photographs are pushed picks them up.

The build order is v1b's (`docs/bench-v1b-uno.md`), which supersedes v1's
because the 74HC parts on the shelf need 5 V logic. The measure-first
list is `docs/wiring.md`'s, and the numbers those steps produce REPLACE
the authored ones in that file: each such step says which claim it
answers, and the notebook carries authored and measured side by side.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "lab-log.jsonl"
PHOTOS = ROOT / "docs" / "lab"

# ------------------------------------------------------------------ output
BOLD, DIM, GREEN, RED, YELLOW, CYAN, OFF = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[0m"
if not sys.stdout.isatty():
    BOLD = DIM = GREEN = RED = YELLOW = CYAN = OFF = ""


def hr(ch="-"):
    print(DIM + ch * 72 + OFF)


def say(s=""):
    print(s)


def ask(prompt, default=None):
    d = f" [{default}]" if default is not None else ""
    try:
        v = input(f"{CYAN}{prompt}{d}: {OFF}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("stopped")
    return v or (default if default is not None else "")


def pause(prompt="Press Enter when ready"):
    try:
        input(f"{CYAN}{prompt}{OFF} ")
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("stopped")


def ask_float(prompt, unit=""):
    while True:
        v = ask(f"{prompt} ({unit})" if unit else prompt)
        if v.lower() in ("skip", "s"):
            return None
        try:
            return float(v.replace(",", "").rstrip("Vvmsµu"))
        except ValueError:
            say(f"  {YELLOW}a number, please, or 'skip'{OFF}")


def ask_yes(prompt):
    while True:
        v = ask(f"{prompt} (y/n)").lower()
        if v.startswith("y"):
            return True
        if v.startswith("n"):
            return False


# ------------------------------------------------------------ instruments
def scope_address(explicit=None):
    """--scope, then $SCOPE, then the first address in bench.local.md,
    which is gitignored and is the only place the address lives."""
    if explicit:
        return explicit
    if os.environ.get("SCOPE"):
        return os.environ["SCOPE"]
    local = ROOT / "bench.local.md"
    if local.exists():
        text = local.read_text()
        # An address with the SCPI port on it beats a bare one: that file
        # also carries the address the scope used to be on, and picking
        # the wrong one looks exactly like an instrument that is off.
        m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}):5555\b", text) or re.search(
            r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text)
        if m:
            return m.group(1)
    return None


def load_scope_class():
    spec = importlib.util.spec_from_file_location("headd", ROOT / "head" / "headd.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Scope


class Bench:
    """Whatever hardware is actually present, and the reasons it is not."""

    def __init__(self, args):
        self.args = args
        self.scope = None
        self.scope_why = "not tried"
        self.serial = None
        self.serial_why = "not tried"

    def get_scope(self):
        if self.args.no_scope:
            self.scope_why = "--no-scope"
            return None
        if self.scope is not None:
            return self.scope
        addr = scope_address(self.args.scope)
        if not addr:
            self.scope_why = "no address: pass --scope, set $SCOPE, or put it in bench.local.md"
            return None
        try:
            self.scope = load_scope_class()(addr, tries=3)
            self.scope_why = "connected"
        except Exception as e:  # noqa: BLE001
            self.scope_why = f"{addr}: {e}"
            self.scope = None
        return self.scope

    def bridge_port(self):
        if self.args.bridge:
            return self.args.bridge
        if os.environ.get("BRIDGE"):
            return os.environ["BRIDGE"]
        found = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        return found[0] if found else None

    def get_serial(self, baud=115200):
        """The bridge's serial port, local or over the LAN.

        A port with `://` in it is handed to pyserial's URL handler, so
        `socket://<pi>:6545` reaches an Arduino plugged into the
        Raspberry Pi that `head/serial-bridge.py` is running on. That is
        the arrangement the plan describes and the one the bench uses:
        the Pi holds the hardware, this workstation holds the model, the
        log and the record. Either way the board resets as the port
        opens, so the wait below is the same."""
        if self.serial is not None:
            return self.serial
        port = self.bridge_port()
        if not port:
            self.serial_why = ("no /dev/ttyACM* or /dev/ttyUSB* here, and no --bridge given. Plug the UNO "
                               "into this workstation, or point --bridge at the Pi it is on "
                               "(socket://<host>:6545, with head/serial-bridge.py running there)")
            return None
        remote = "://" in port
        if not remote and not os.access(port, os.R_OK | os.W_OK):
            self.serial_why = (f"{port} is not readable by you. Fix: sudo usermod -aG dialout $USER, "
                               "then log out and back in (a new shell is not enough)")
            return None
        try:
            import serial
            if remote:
                self.serial = serial.serial_for_url(port, baudrate=baud, timeout=1.0)
            else:
                self.serial = serial.Serial(port, baud, timeout=1.0)
            time.sleep(2.5)  # the UNO resets when the port opens, near or far
            self.serial.reset_input_buffer()
            self.serial_why = f"open on {port}"
        except Exception as e:  # noqa: BLE001
            self.serial_why = f"{port}: {e}"
            self.serial = None
        return self.serial


def bridge_cmd(ser, line, wait=1.2, limit=400):
    """Send a command and read for a bounded window.

    The window is the point. The bridge streams an L line per poll,
    sixty a second, forever, so draining "until nothing is waiting"
    never returns while a console is running. Found by rehearsing this
    tool against tools/fake-bridge.py, which streams the same way."""
    ser.reset_input_buffer()
    ser.write((line + "\n").encode())
    ser.flush()
    out = []
    end = time.time() + wait
    while time.time() < end and len(out) < limit:
        l = ser.readline().decode(errors="replace").rstrip()
        if l:
            out.append(l)
    return out


def bridge_stream(ser, seconds):
    """Every line the bridge sends for a while."""
    out = []
    end = time.time() + seconds
    while time.time() < end:
        line = ser.readline().decode(errors="replace").rstrip()
        if line:
            out.append(line)
    return out


# -------------------------------------------------------------- waveforms
def edges(sig, thr):
    import numpy as np
    above = sig > thr
    d = np.diff(above.astype(np.int8))
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def measure_port(latch, clock, rate):
    """The four numbers the plan says replace the authored ones: the latch
    pulse width, the clock pulse width, the clocks per latch, and the
    polls per second. Levels are thresholded at each channel's own
    midpoint, so a 5 V line and a 3.3 V line both read correctly."""
    import numpy as np
    out = {}
    for name, sig in (("latch", latch), ("clock", clock)):
        lo, hi = float(np.percentile(sig, 2)), float(np.percentile(sig, 98))
        out[f"{name}_low_code"], out[f"{name}_high_code"] = lo, hi
        if hi - lo < 20:
            return {"error": f"the {name} channel is flat ({lo:.0f} to {hi:.0f} of 255): is the probe on, and the console running?"}
    lt = (np.percentile(latch, 2) + np.percentile(latch, 98)) / 2
    ct = (np.percentile(clock, 2) + np.percentile(clock, 98)) / 2
    lr, lf = edges(latch, lt)
    cf, cr = edges(clock, ct)[1], edges(clock, ct)[0]
    if len(lr) < 2:
        return {"error": f"only {len(lr)} latch rises in the record: is a game running and polling?"}
    # Latch: high time, and the interval between rises.
    widths = []
    for r in lr:
        f = lf[lf > r]
        if len(f):
            widths.append((f[0] - r) / rate)
    periods = np.diff(lr) / rate
    out["latch_high_us"] = float(np.median(widths)) * 1e6 if widths else None
    out["latch_period_ms"] = float(np.median(periods)) * 1e3
    out["polls_per_s"] = 1.0 / float(np.median(periods))
    out["latches_seen"] = int(len(lr))
    # Clock: low time (the console clocks by pulling low), and how many
    # fall between one latch rise and the next.
    lows = []
    for f in cf:
        r = cr[cr > f]
        if len(r):
            lows.append((r[0] - f) / rate)
    out["clock_low_us"] = float(np.median(lows)) * 1e6 if lows else None
    if len(cf) > 2:
        out["clock_period_us"] = float(np.median(np.diff(cf))) * 1e6
    per = []
    for a, b in zip(lr[:-1], lr[1:]):
        per.append(int(((cf >= a) & (cf < b)).sum()))
    out["clocks_per_latch"] = per[: 20]
    if per:
        vals, counts = np.unique(per, return_counts=True)
        out["clocks_per_latch_mode"] = int(vals[counts.argmax()])
        out["clocks_per_latch_hist"] = {int(v): int(c) for v, c in zip(vals, counts)}
    return out


# ------------------------------------------------------------------ steps
# Each step: what to do, then a check that measures rather than asks.
# "replaces" names the authored claim the step's number supersedes.
def S(sid, stage, title, do, check, photos=(), replaces=None, needs=()):
    return dict(id=sid, stage=stage, title=title, do=do, check=check, photos=list(photos), replaces=replaces, needs=list(needs))


STEPS = [
    S("0.1", "Instruments", "The scope answers, and says what it is",
      ["Power the scope and put it on the LAN.",
       "Its address belongs in bench.local.md, which git ignores. Nothing else needs it."],
      "scope_idn"),
    S("0.2", "Instruments", "The workstation can open a serial port",
      ["Plug the Arduino UNO in, with nothing else connected to it yet: no chips, no console, no pad. This step only proves the port opens.",
       "It can be plugged into this workstation, or into the Raspberry Pi that is the head. For the Pi, run head/serial-bridge.py there and point the tools at it:",
       "$ python3 tools/bringup.py --session 1 --bridge socket://<pi>:6545"],
      "serial_open",
      photos=["00-uno-bare.jpg"]),
    S("0.3", "Instruments", "The bridge firmware is on the UNO and answers STATUS",
      ["Flash the sketch, putting your own port after -p:",
       "$ arduino-cli compile --fqbn arduino:avr:uno firmware/bridge-uno",
       "$ arduino-cli upload  --fqbn arduino:avr:uno -p /dev/ttyACM0 firmware/bridge-uno"],
      "bridge_hello"),

    S("1.1", "The harness", "The controller harness's colours against the port's pins",
      ["Console UNPLUGGED from the wall. Open it if it is not already.",
       "Two ways to attach a colour to a pin number, and the record keeps which you used. The port housing has its pin numbers moulded into the plastic beside the crimp terminals, four on one row and three on the other: photograph both rows and read them off. Or find the white header where the harness lands on the board and ring each pin out to the socket with the meter.",
       "The moulded numbers are the connector telling you its own numbering, which is worth more than a colour convention. What they do not tell you is whether the harness carries each pin to the board header unswapped. Only the meter does that, so 'both' is the strongest answer.",
       "Port pinout, looking into the socket: 1 GND, 2 CLK, 3 OUT0, 4 D0, 5 D3, 6 D4, 7 +5V.",
       "Colours are not evidence on their own. Every pin gets a number from the connector or from the meter, never from what the colour usually means.",
       "If a breakout is spliced onto the harness, this step maps its leads too, because the breakout is what a probe actually lands on. Those leads are new wire in whatever colours were to hand and carry no convention at all.",
       "Two breakout leads the same colour is the case to watch: a probe's ground clip and its tip go on adjacent leads, and a clip on a driven line grounds it. This step refuses a shared colour that was only read off the housing, and asks you to ring those leads out from the board header first."],
      "harness_map",
      photos=["01-port-housing-pins-1-4.jpg", "01-port-housing-pins-5-7.jpg", "01-board-header.jpg",
              "01-breakout-map-controller.jpg"],
      replaces="wiring.md's port table is a published pinout until this step confirms it on THIS board"),
    S("1.2", "The harness", "The port's idle levels with the console on",
      ["Console powered, NOTHING plugged into the port you are measuring.",
       "Meter black on port pin 1 (GND). Measure pins 7, 3, 2 and 4 in turn.",
       "Expect: pin 7 near 5 V, pins 3 and 2 idle, pin 4 pulled up."],
      "port_levels",
      photos=["01-meter-on-port.jpg"]),

    S("2.1", "The part's own timing", "The scope on an original pad's port, a game running",
      ["Put an original pad in the console's OTHER port and start a game that polls.",
       "Scope CH1 probe on that port's pin 3 (OUT0, the latch).",
       "Scope CH2 probe on that port's pin 2 (CLK).",
       "Both probe grounds on port pin 1. Probes at 1x if they have a switch.",
       "This is the measurement that replaces four authored numbers at once."],
      "scope_port_timing",
      photos=["02-probes-on-port.jpg", "02-scope-screen.jpg"],
      replaces="wiring.md's authored 'latch high a few us, clock low a few hundred ns, ~7 us between clocks, 60 polls/s'"),

    S("3.1", "The console side", "U1 and U2 on the board, links on H..A, the pattern on QH",
      ["Console OFF. Build only the console-facing half on the breadboard:",
       "  74HC04 (U1): pin 14 to port +5V, pin 7 to GND, pin 1 from port pin 3 (OUT0).",
       "  74HC165 (U2): pin 16 to +5V, pin 8 to GND, pin 15 (/CE) to GND, pin 10 (DS) to GND, pin 1 (/PL) from U1 pin 2, pin 2 (CP) from port pin 2 (CLK), pin 9 (QH) to port pin 4 (D0).",
       "  100 nF across each chip's supply pins.",
       "  Wire links on the eight inputs to make a KNOWN byte. In pad order A, B, Select, Start, Up, Down, Left, Right those are pins 6, 5, 4, 3, 14, 13, 12, 11, and LOW is pressed.",
       "Scope CH1 still on OUT0, CH2 moved to QH (U2 pin 9). Console on, game running."],
      "scope_qh_pattern",
      photos=["03-console-side-built.jpg", "03-qh-on-scope.jpg"]),

    S("4.1", "The UNO side", "The UNO drives the 595, measured on its outputs",
      ["Console OFF and its port half left alone. On the UNO's side of the board:",
       "  74HC595 (U3): pin 16 to the UNO's 5V, pin 8 to GND, pin 13 (/OE) to GND, pin 10 (/SRCLR) to 5V, pin 14 (SER) from UNO D11, pin 11 (SRCLK) from UNO D13, pin 12 (RCLK) from UNO D10.",
       "  100 nF across its supply pins.",
       "Do NOT join U3's outputs to U2's inputs yet. Meter on QA (pin 15), black on GND."],
      "bridge_set_byte",
      photos=["04-uno-and-595.jpg"]),
    S("4.2", "The UNO side", "The original pad polled by the bridge at 5 V",
      ["Plug the console's spare port housing into the bridge's pad side:",
       "  pad pin 1 to GND, pin 7 to the UNO's 5V, pin 3 (OUT0) to UNO D6, pin 2 (CLK) to UNO D7, pin 4 (D0) to UNO D8.",
       "Plug an original pad into it. Console still off.",
       "You will be asked to hold buttons; the bridge's own poll should follow them."],
      "bridge_pad_follows",
      photos=["04-pad-on-bridge.jpg"]),

    S("5.1", "Joined", "The two halves joined, eight clocks per latch on a game",
      ["Console OFF. Remove the wire links from U2's inputs and join the halves:",
       "  U3 QA..QH (pins 15, 1, 2, 3, 4, 5, 6, 7) to U2 H..A (pins 6, 5, 4, 3, 14, 13, 12, 11).",
       "  UNO D5 to port pin 3 (OUT0). UNO D2 to port pin 2 (CLK).",
       "  The console's GND, the breadboard's GND and the UNO's GND are one net.",
       "Console on, a game running that polls the pad, MODE PASS.",
       "This is B0's first gate: eight clocks on every poll."],
      "bridge_eight_clocks",
      photos=["05-bridge-joined.jpg", "05-console-running.jpg"],
      replaces="the plan's B0 gate 1, which is the first thing the part gets to answer"),
    S("5.2", "Joined", "A pressed button reaches the console through the bridge",
      ["Same setup. You will be asked to hold a button; the game should see it,",
       "and the bridge's log should carry the same byte at the same latches."],
      "bridge_pass_through",
      photos=["05-button-through.jpg"]),

    S("6.1", "The head's hands", "The trigger reaches the scope",
      ["UNO D3 through a 100 ohm resistor to the scope's rear EXT TRIG.",
       "Check the EXT TRIG input's rating first; if 5 V is over it, a 2:1 divider after the resistor."],
      "trigger_reaches_scope",
      photos=["06-trigger-cable.jpg"]),
    S("6.2", "The head's hands", "The reset optocoupler pulses the console",
      ["Console on. Find the reset button's two pads; meter which is ground and which is pulled up.",
       "PC817 module: OUT to the pulled-up pad, its GND to the ground pad, VCC unconnected, and the Pi's GPIO17 to INPUT + with INPUT - to the Pi's GND."],
      "reset_pulse",
      photos=["06-reset-pads.jpg", "06-breakout-map-power-reset.jpg"]),
    S("6.3", "The head's hands", "The power relay switches the console",
      ["MAINS SAFETY: the contact goes in series with ONE lead of the low-voltage adapter cable, between the adapter and the console's DC jack. Never the mains side, and never both leads.",
       "Relay module VCC to the Pi's 5V pin, IN to GPIO27 (active low), GND to the Pi's GND."],
      "power_relay",
      photos=["06-relay-inline.jpg"]),
]

BY_ID = {s["id"]: s for s in STEPS}

# One sitting at the bench is one command. The steps inside a session
# share a setup, so splitting them across invocations only means wiring
# the same thing twice. `docs/build-guide.md` is these five, written out
# with what to wire, and is generated from this table.
SESSIONS = [
    (1, "Instruments", "Nothing is wired. The scope answers, the UNO's port opens, the sketch is on it.",
     ["0.1", "0.2", "0.3"]),
    (2, "The console, measured", "Still nothing built. A meter and two probes on the console you already have.",
     ["1.1", "1.2", "2.1"]),
    (3, "The bridge, built", "The breadboard, in two halves that are tested apart before they are joined.",
     ["3.1", "4.1", "4.2"]),
    (4, "Joined", "The halves wired together. B0's first gate.",
     ["5.1", "5.2"]),
    (5, "The head's hands", "The trigger, the reset optocoupler and the power relay.",
     ["6.1", "6.2", "6.3"]),
]
SESSION_OF = {sid: n for n, _t, _d, ids in SESSIONS for sid in ids}


# ----------------------------------------------------------------- checks
def check_scope_idn(bench, step):
    sc = bench.get_scope()
    if not sc:
        return "skip", {"why": bench.scope_why}, f"no scope: {bench.scope_why}"
    parts = sc.idn.split(",")
    d = {"idn": sc.idn, "model": parts[1] if len(parts) > 1 else "?", "firmware": parts[3] if len(parts) > 3 else "?"}
    return "pass", d, f"{d['model']}, firmware {d['firmware']}"


def check_serial_open(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    return "pass", {"port": bench.bridge_port()}, f"{bench.bridge_port()} opens"


def check_bridge_hello(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    out = bridge_cmd(ser, "STATUS", wait=1.0)
    status = [l for l in out if l.startswith("#")]
    if not any("mode" in l for l in status):
        return "fail", {"reply": out}, f"STATUS got {out!r}: is the v1b sketch flashed?"
    return "pass", {"status": status}, status[0]


# How a colour got attached to a pin number. The two are not equally
# strong and the record has to say which was used: a moulded number on
# the housing is the connector telling you its own numbering, while a
# meter rung from the board header proves the harness carries it there.
METHODS = {
    "meter": "rung out with a meter, header to socket",
    "moulded": "read off the pin numbers moulded into the port housing",
    "both": "read off the moulded numbers and confirmed with a meter",
}

PORT_PINS = ((1, "GND"), (2, "CLK"), (3, "OUT0"), (4, "D0"), (5, "D3"), (6, "D4"), (7, "+5V"))


def _named(colour):
    """A colour that is actually a colour. 'skip' leaves a pin blank in the
    harness map; 'nc' says a breakout does not bring that pin out. Both are
    answers, and neither is a colour."""
    return bool(colour) and colour.strip().lower() not in ("skip", "s", "nc", "none", "-")


def check_harness_map(bench, step):
    say(f"  {DIM}How was each colour attached to its pin number?{OFF}")
    for k, v in METHODS.items():
        say(f"    {k}: {v}")
    method = ask("  method", "meter")
    if method not in METHODS:
        return "fail", {"method": method}, f"{method!r} is not one of {', '.join(METHODS)}"
    say(f"  {DIM}Now the colour at each pin, or 'skip' to leave one blank.{OFF}")
    m = {}
    for pin, name in PORT_PINS:
        m[f"pin{pin}"] = {"name": name, "colour": ask(f"  pin {pin} ({name}) colour")}
    named = [k for k, v in m.items() if _named(v["colour"])]
    d = {"map": m, "method": method}
    if len(named) < 4:
        return "fail", d, f"only {len(named)} pins mapped; the four that carry signal are the minimum"
    notes = []
    if method == "moulded":
        # The housing's numbering is the housing's. What it does NOT show
        # is whether the harness carries each pin to the board header
        # unswapped, nor that the published function table is right for
        # this board. Step 1.2's supply reading is what tests both.
        notes.append("the numbering is the housing's own, and step 1.2's +5V reading is what tests it")

    # A breakout spliced onto the harness is what a probe actually lands
    # on, so a map that stops at the harness is a map of something nobody
    # touches. Its leads are new wire in somebody's own colours and carry
    # no convention at all.
    if ask_yes("  Is a breakout spliced onto this harness"):
        say(f"  {DIM}The breakout's lead at each pin: a colour, or 'nc' where the pin is not brought out.{OFF}")
        b = {}
        for pin, name in PORT_PINS:
            b[f"pin{pin}"] = {"name": name, "colour": ask(f"  pin {pin} ({name}) breakout lead")}
        d["breakout"] = b
        for k in ("pin1", "pin2", "pin3", "pin4"):
            if not _named(b[k]["colour"]):
                return "fail", d, (f"{b[k]['name']} is not on the breakout. GND, CLK, OUT0 and D0 are the four "
                                   "the bridge touches; a breakout missing one of them cannot carry it")
        by_colour = {}
        for k, v in b.items():
            if _named(v["colour"]):
                by_colour.setdefault(v["colour"].strip().lower(), []).append(int(k[3:]))
        shared = sorted([c, sorted(p)] for c, p in by_colour.items() if len(p) > 1)
        if shared:
            # Two leads the same colour cannot be told apart by looking,
            # and a probe's ground clip and its tip are what go on them.
            # A clip on the wrong one grounds a driven line. Only a meter
            # separates them, so the method has to have used one.
            d["shared"] = shared
            words = "; ".join(f"pins {' and '.join(str(x) for x in p)} are both {c}" for c, p in shared)
            if method == "moulded":
                return "fail", d, (f"{words}. A shared colour cannot be read off the housing: ring those leads "
                                   "out from the board header before a probe goes near them")
            notes.append(f"{words}, told apart with the meter")
        d["supply_out"] = _named(b["pin7"]["colour"])
        if not d["supply_out"]:
            notes.append("+5V is not brought out, so step 1.2's supply reading is taken at the "
                         "housing or the board header, not the breakout")

    say(f"  {DIM}Put this table into bench.local.md too; it is board-specific and not committed.{OFF}")
    tail = ("; " + "; ".join(notes)) if notes else ""
    return "pass", d, f"{len(named)} of 7 pins mapped, {METHODS[method]}{tail}"


def check_port_levels(bench, step):
    v = {}
    v["pin7_v"] = ask_float("  pin 7 (+5V) to pin 1", "V")
    v["pin3_v"] = ask_float("  pin 3 (OUT0) idle", "V")
    v["pin2_v"] = ask_float("  pin 2 (CLK) idle", "V")
    v["pin4_v"] = ask_float("  pin 4 (D0) idle", "V")
    if v["pin7_v"] is None:
        return "fail", v, "the supply pin is the one that must not be skipped"
    if not 4.5 <= v["pin7_v"] <= 5.5:
        return "fail", v, (f"pin 7 reads {v['pin7_v']} V, not about 5. Either the harness map is wrong "
                           "or the console's supply is. Do not build onto this.")
    return "pass", v, f"+5V rail {v['pin7_v']} V; OUT0 {v['pin3_v']}, CLK {v['pin2_v']}, D0 {v['pin4_v']}"


def _capture_two(bench, step, name, note):
    """Arm on the latch line and read both channels: the shared body of
    the two scope steps."""
    sc = bench.get_scope()
    if not sc:
        return None, ("skip", {"why": bench.scope_why}, f"no scope: {bench.scope_why}")
    out = ROOT / "captures"
    out.mkdir(exist_ok=True)
    try:
        sc.save_setup()
        sc.arm(chs=[1, 2], scale=1.0, offset=-2.0, source="CH1", tb=0.005, depth=12_000_000)
        say(f"  {DIM}armed, waiting for a latch pulse...{OFF}")
        for _ in range(60):
            if sc.triggered():
                break
            time.sleep(0.5)
        else:
            return None, ("fail", {}, "no trigger in 30 s: is the console polling, and is CH1 on OUT0?")
        info = sc.read_record([1, 2], out, name, note)
    finally:
        try:
            sc.restore_setup()
        except Exception:  # noqa: BLE001
            pass
    return info, None


def check_scope_port_timing(bench, step):
    import numpy as np
    info, early = _capture_two(bench, step, "bringup-port-timing", "bring-up 2.1: an original pad's port while a game polls")
    if early:
        return early
    latch = np.fromfile(ROOT / "captures" / info["files"][1], dtype=np.uint8).astype(np.float32)
    clock = np.fromfile(ROOT / "captures" / info["files"][2], dtype=np.uint8).astype(np.float32)
    m = measure_port(latch, clock, info["rate"])
    if "error" in m:
        return "fail", m, m["error"]
    m["capture"] = f"captures/{info['files'][1]}"
    ok = m.get("clocks_per_latch_mode") == 8
    line = (f"latch high {m['latch_high_us']:.2f} us, clock low {m['clock_low_us']:.3f} us, "
            f"clock period {m.get('clock_period_us', float('nan')):.2f} us, "
            f"{m['polls_per_s']:.2f} polls/s, {m.get('clocks_per_latch_mode')} clocks per latch "
            f"over {m['latches_seen']} latches")
    return ("pass" if ok else "fail"), m, line + ("" if ok else "  <- expected 8 clocks per latch")


def check_scope_qh_pattern(bench, step):
    import numpy as np
    byte = ask("  the byte your wire links make, hex (bit 0 = A, set = pressed)", "01")
    try:
        want = int(byte, 16) & 0xFF
    except ValueError:
        return "fail", {"byte": byte}, f"{byte!r} is not hex"
    info, early = _capture_two(bench, step, "bringup-qh", "bring-up 3.1: QH against a known byte")
    if early:
        return early
    latch = np.fromfile(ROOT / "captures" / info["files"][1], dtype=np.uint8).astype(np.float32)
    qh = np.fromfile(ROOT / "captures" / info["files"][2], dtype=np.uint8).astype(np.float32)
    rate = info["rate"]
    lt = (np.percentile(latch, 2) + np.percentile(latch, 98)) / 2
    qt = (np.percentile(qh, 2) + np.percentile(qh, 98)) / 2
    if np.percentile(qh, 98) - np.percentile(qh, 2) < 20:
        return "fail", {"note": "QH flat"}, "QH never moves: check /CE to GND, /PL from the inverter, and the links"
    lr, _ = edges(latch, lt)
    if len(lr) < 2:
        return "fail", {}, "no latch pulses: is the console polling?"
    # Read the eight bits after one latch: sample QH just before each of
    # the clock line's rises is not available here (CH2 is QH), so sample
    # at the midpoints of the eight intervals after the latch falls.
    got = None
    for r in lr[1:6]:
        seg = qh[r: r + int(200e-6 * rate)]
        if len(seg) < 100:
            continue
        # The console clocks eight bits in about 100 us; sample evenly.
        step_n = len(seg) // 9
        bits = [1 if seg[step_n * (i + 1) - step_n // 3] < qt else 0 for i in range(8)]
        got = sum(b << i for i, b in enumerate(bits))
        break
    d = {"want": want, "got": got, "capture": f"captures/{info['files'][2]}"}
    if got is None:
        return "fail", d, "could not find eight bits after a latch"
    ok = got == want
    return ("pass" if ok else "fail"), d, (f"QH reads ${got:02x}, links say ${want:02x}"
                                           + ("" if ok else "  <- check the input order, H is A"))


def check_bridge_set_byte(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    bridge_cmd(ser, "MODE INJECT")
    bridge_cmd(ser, "SET 08")
    st = bridge_cmd(ser, "STATUS", wait=1.0)
    held = None
    for l in st:
        m = re.search(r"held ([0-9a-f]{2})", l)
        if m:
            held = m.group(1)
    say(f"  {DIM}SET 08 is Start pressed: QD (pin 3) should be LOW, the other seven HIGH.{OFF}")
    qd = ask_float("  U3 QD (pin 3)", "V")
    qa = ask_float("  U3 QA (pin 15)", "V")
    d = {"status_held": held, "qd_v": qd, "qa_v": qa}
    if held != "08":
        return "fail", d, f"STATUS reports held {held}, not 08"
    if qd is None or qa is None:
        return "fail", d, "both outputs need measuring; a byte on the wire is the point of this step"
    if qd > 1.0 or qa < 3.5:
        return "fail", d, f"QD {qd} V and QA {qa} V: pressed must be LOW and the rest HIGH. Check the bit order."
    return "pass", d, f"held 08; QD {qd} V low, QA {qa} V high"


def check_bridge_pad_follows(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    bridge_cmd(ser, "MODE PASS")
    seen = {}
    for name, mask in (("A", 0x01), ("Start", 0x08), ("Right", 0x80)):
        say(f"  {BOLD}Hold {name} down now.{OFF}")
        pause("  Press Enter while you are holding it")
        st = bridge_cmd(ser, "STATUS", wait=1.0)
        pad = None
        for l in st:
            m = re.search(r"pad ([0-9a-f]{2})", l)
            if m:
                pad = int(m.group(1), 16)
        seen[name] = {"pad": f"{pad:02x}" if pad is not None else None, "mask": f"{mask:02x}",
                      "bit_set": bool(pad is not None and pad & mask)}
        say(f"    pad reads ${pad:02x}" if pad is not None else "    no pad byte in STATUS")
    good = [k for k, v in seen.items() if v["bit_set"]]
    if len(good) < 3:
        bad = [k for k in seen if k not in good]
        return "fail", seen, f"{', '.join(bad)} did not appear in the pad byte: check D0, the poll lines, and 5 V on pad pin 7"
    return "pass", seen, "A, Start and Right each set their own bit"


def check_bridge_eight_clocks(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    bridge_cmd(ser, "MODE PASS")
    bridge_cmd(ser, "RESET")
    say(f"  {DIM}listening to the bridge for 20 s while the game polls...{OFF}")
    lines = bridge_stream(ser, 20.0)
    polls = []
    for l in lines:
        f = l.split()
        if len(f) == 4 and f[0] == "L":
            polls.append(int(f[3]))
    if len(polls) < 100:
        return "fail", {"polls": len(polls), "sample": lines[:5]}, \
            f"only {len(polls)} polls in 20 s: is a game running, and are D5 and D2 on OUT0 and CLK?"
    from collections import Counter
    hist = Counter(polls)
    eights = hist.get(8, 0)
    d = {"polls": len(polls), "hist": {int(k): int(v) for k, v in sorted(hist.items())},
         "polls_per_s": len(polls) / 20.0, "eight_fraction": eights / len(polls)}
    ok = eights == len(polls)
    line = f"{len(polls)} polls in 20 s ({d['polls_per_s']:.1f}/s), clocks per poll {dict(sorted(hist.items()))}"
    if ok:
        return "pass", d, line + "  <- B0 gate 1 held"
    return "fail", d, line + f"  <- {len(polls) - eights} polls were not 8 clocks"


def check_bridge_pass_through(bench, step):
    ser = bench.get_serial()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    bridge_cmd(ser, "MODE PASS")
    say(f"  {BOLD}Hold Start (or whatever the game reacts to) down now.{OFF}")
    pause("  Press Enter while you are holding it")
    lines = bridge_stream(ser, 3.0)
    bytes_seen = [f.split()[2] for f in lines if f.startswith("L ") and len(f.split()) == 4]
    reacted = ask_yes("  did the game react")
    d = {"bytes": sorted(set(bytes_seen)), "game_reacted": reacted, "samples": len(bytes_seen)}
    if not bytes_seen:
        return "fail", d, "no polls logged while the button was held"
    if not reacted:
        return "fail", d, f"the bridge logged {sorted(set(bytes_seen))} but the game did not react: check QH to port pin 4"
    return "pass", d, f"the game reacted and the log carried {sorted(set(bytes_seen))} over {len(bytes_seen)} polls"


def check_trigger_reaches_scope(bench, step):
    ser = bench.get_serial()
    sc = bench.get_scope()
    if not ser:
        return "fail", {"why": bench.serial_why}, bench.serial_why
    if not sc:
        return "skip", {"why": bench.scope_why}, f"no scope: {bench.scope_why}"
    try:
        sc.save_setup()
        sc.arm(chs=[1], scale=1.0, offset=-2.0, source="EXT", tb=0.005, depth=12_000_000)
        bridge_cmd(ser, "RESET")
        bridge_cmd(ser, "TRIG 20")
        say(f"  {DIM}armed on EXT TRIG, waiting for latch 20...{OFF}")
        fired = False
        for _ in range(60):
            if sc.triggered():
                fired = True
                break
            time.sleep(0.5)
    finally:
        try:
            sc.restore_setup()
        except Exception:  # noqa: BLE001
            pass
    if not fired:
        return "fail", {}, "the scope did not trigger: check the resistor, the BNC, and EXT TRIG's level (1.5 V, rising)"
    return "pass", {"trig_at_latch": 20}, "TRIG 20 stopped the scope on EXT TRIG"


def check_reset_pulse(bench, step):
    say(f"  {DIM}Which reset pad is ground, and what does the other sit at?{OFF}")
    gnd = ask("  which pad is ground (left/right/other, your words)")
    v = ask_float("  the other pad's level with the console on", "V")
    say(f"  {DIM}Now drive it. On the Pi: gpioset (or the head's RESET word).{OFF}")
    ok = ask_yes("  did the console reset when the pin was pulsed")
    d = {"ground_pad": gnd, "pulled_up_v": v, "console_reset": ok}
    if not ok:
        return "fail", d, "the pulse did not reset the console: check OUT and GND are not swapped"
    return "pass", d, f"the pulled-up pad sits at {v} V and a 100 ms pulse resets the console"


def check_power_relay(bench, step):
    say(f"  {YELLOW}Confirm the contact is in the LOW-VOLTAGE adapter lead, not the mains.{OFF}")
    if not ask_yes("  is the contact on the adapter's output side, in one lead only"):
        return "fail", {"mains_safe": False}, "refused: the relay must not be in the mains lead"
    on = ask_yes("  does the console power up when the relay is driven on")
    off = ask_yes("  and go dark when it is driven off")
    d = {"mains_safe": True, "powers_on": on, "powers_off": off}
    if not (on and off):
        return "fail", d, "the relay does not switch the console cleanly"
    return "pass", d, "the relay switches the console on and off, in the adapter lead"


CHECKS = {k[6:]: v for k, v in list(globals().items()) if k.startswith("check_")}


# ------------------------------------------------------------------- log
def read_log():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def append(entry):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def latest_state():
    """The last outcome recorded for each step."""
    st = {}
    for e in read_log():
        st[e["step"]] = e
    return st


# ------------------------------------------------------------------- run
def run_step(bench, step, args):
    hr("=")
    say(f"{BOLD}Step {step['id']}  {step['title']}{OFF}")
    say(f"{DIM}{step['stage']}{OFF}")
    if step["replaces"]:
        say(f"{DIM}Answers: {step['replaces']}{OFF}")
    hr()
    for line in step["do"]:
        if line.startswith("$ "):
            say(f"    {BOLD}{line[2:]}{OFF}")
        elif line.startswith("  "):
            say(textwrap.fill(line.strip(), 68, initial_indent="    - ", subsequent_indent="      "))
        else:
            say(textwrap.fill(line, 70, initial_indent="  ", subsequent_indent="  "))
    say()
    pause()
    fn = CHECKS.get(step["check"])
    if fn is None:
        return {"state": "fail", "data": {}, "line": f"no check named {step['check']}"}
    try:
        state, data, line = fn(bench, step)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        state, data, line = "fail", {"exception": repr(e)}, f"the check raised: {e}"
    colour = {"pass": GREEN, "fail": RED, "skip": YELLOW}[state]
    say(f"  {colour}{state.upper()}{OFF}  {line}")
    # Photographs are named, never waited on. Stopping the run for a
    # keystroke per picture was most of the interruption and bought
    # nothing: the notebook embeds a photograph when the file arrives and
    # says it is pending until then, whichever order that happens in.
    taken = []
    for name in step["photos"]:
        dest = PHOTOS / name
        mark = f"{GREEN}already there{OFF}" if dest.exists() else f"{YELLOW}wanted{OFF}"
        say(f"  Photo {mark}: {DIM}docs/lab/{name}{OFF}  ({step['title'].lower()})")
        taken.append({"file": f"docs/lab/{name}", "present": dest.exists()})
    return {"state": state, "data": data, "line": line, "photos": taken}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--step", help="run just this step id")
    ap.add_argument("--session", type=int, help="run one whole sitting: 1 to 5, see docs/build-guide.md")
    ap.add_argument("--from", dest="from_", help="start at this step id")
    ap.add_argument("--scope", help="the scope's address (else $SCOPE, else bench.local.md)")
    ap.add_argument("--no-scope", action="store_true", help="the scope is absent: its steps SKIP, they do not pass")
    ap.add_argument("--bridge", default=None,
                    help="the UNO's serial port: a local device, a tools/fake-bridge.py pty, or "
                         "socket://<host>:6545 for one on the Pi running head/serial-bridge.py. "
                         "$BRIDGE is used if this is not given.")
    ap.add_argument("--operator", default=os.environ.get("USER", "?"))
    ap.add_argument("--rehearse", action="store_true",
                    help="a dry run against stand-ins (tools/fake-bridge.py): logged, but marked so the "
                         "notebook never counts it as bench work")
    a = ap.parse_args()

    state = latest_state()
    if a.list:
        stage = None
        for s in STEPS:
            if s["stage"] != stage:
                stage = s["stage"]
                say(f"\n{BOLD}{stage}{OFF}")
            e = state.get(s["id"])
            if e and e.get("rehearsal"):
                mark = f"{DIM}dry {e['state'][:4]}{OFF}"
            else:
                mark = {"pass": f"{GREEN}pass{OFF}", "fail": f"{RED}fail{OFF}", "skip": f"{YELLOW}skip{OFF}"}.get(
                    e["state"] if e else "", f"{DIM}....{OFF}")
            say(f"  {mark}  {s['id']}  {s['title']}")
        say()
        done = sum(1 for s in STEPS
                   if state.get(s["id"], {}).get("state") == "pass" and not state.get(s["id"], {}).get("rehearsal"))
        dry = sum(1 for s in STEPS if state.get(s["id"], {}).get("rehearsal"))
        tail = f"  ({dry} rehearsed against stand-ins, which does not count)" if dry else ""
        say(f"{done} of {len(STEPS)} steps hold on hardware.{tail}")
        say(f"{DIM}Log: docs/lab-log.jsonl. Notebook: python3 tools/lab-notebook.py{OFF}")
        return 0

    if a.session:
        match = [x for x in SESSIONS if x[0] == a.session]
        if not match:
            raise SystemExit(f"no session {a.session}; there are {len(SESSIONS)}")
        n, t, d, ids = match[0]
        todo = [BY_ID[i] for i in ids]
        say(f"{BOLD}Session {n}: {t}{OFF}")
        say(f"{DIM}{d}{OFF}")
    elif a.step:
        todo = [BY_ID[a.step]] if a.step in BY_ID else []
        if not todo:
            raise SystemExit(f"no step {a.step}; try --list")
    elif a.from_:
        ids = [s["id"] for s in STEPS]
        if a.from_ not in ids:
            raise SystemExit(f"no step {a.from_}; try --list")
        todo = STEPS[ids.index(a.from_):]
    else:
        todo = [s for s in STEPS
                if not (state.get(s["id"], {}).get("state") == "pass"
                        and not state.get(s["id"], {}).get("rehearsal"))]
        if not todo:
            say(f"{GREEN}Every step holds.{OFF} Re-run one with --step, or see --list.")
            return 0

    bench = Bench(a)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    if a.rehearse:
        say(f"{YELLOW}REHEARSAL{OFF}: these attempts are marked and the notebook will not count them as bench work.")
    say(f"{BOLD}nes-bench bring-up{OFF}  operator {a.operator}  {len(todo)} step(s) to go")
    say(f"{DIM}Ctrl-C stops. Nothing is lost: every attempt is appended to docs/lab-log.jsonl.{OFF}")

    for s in todo:
        r = run_step(bench, s, a)
        append({"step": s["id"], "title": s["title"], "stage": s["stage"], "replaces": s["replaces"],
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "operator": a.operator, "rehearsal": bool(a.rehearse),
                "state": r["state"], "summary": r["line"], "data": r["data"], "photos": r["photos"]})
        if r["state"] == "fail":
            hr("=")
            say(f"{RED}Stopped at {s['id']}.{OFF} The next step assumes this one, so fix it and run:")
            say(f"    python3 tools/bringup.py --step {s['id']}")
            if SESSION_OF.get(s["id"]):
                say(f"    python3 tools/bringup.py --session {SESSION_OF[s['id']]}   # or the whole sitting again")
            return 1
    hr("=")
    say(f"{GREEN}Done.{OFF}")
    wanted = [p["file"] for s in todo for p in [{"file": f"docs/lab/{n}"} for n in s["photos"]]
              if not (ROOT / p["file"]).exists()]
    if wanted:
        say(f"\n{BOLD}Photographs still wanted{OFF} (save under exactly these names, then push):")
        for w in wanted:
            say(f"  {w}")
    say(f"\n{BOLD}Then:{OFF}")
    say("  python3 tools/lab-notebook.py     # fold it into the notebook")
    if a.session and a.session < len(SESSIONS):
        nxt = SESSIONS[a.session][0]
        say(f"  python3 tools/bringup.py --session {nxt}   # {SESSIONS[a.session][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
