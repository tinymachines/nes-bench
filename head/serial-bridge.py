#!/usr/bin/env python3
"""The bridge's serial port, over the LAN, with nothing installed.

  python3 head/serial-bridge.py --port /dev/ttyACM0 --listen 0.0.0.0:6545

Runs on the Raspberry Pi that the Arduino is plugged into. Standard
library only, Python 3.7 and up: this machine deliberately resolves DNS
through DNSCrypt resolvers on another subnet, so from the bench network
it can reach neither apt nor GitHub, and nothing can be installed on it.
That is a feature of the setup rather than a fault, so the tooling comes
to the port instead of the other way round.

It gives the workstation two things at once, over one TCP port:

  the tools     tools/bringup.py --bridge socket://<pi>:6545
                (pyserial understands socket:// with no extra code)
  flashing      avrdude -c arduino -p atmega328p -P net:<pi>:6545 \\
                        -U flash:w:bridge-uno.ino.hex:i

**The serial port is opened when a client connects and closed when it
goes away**, rather than held open. That is not tidiness: opening the
port asserts DTR, which resets an Arduino Uno into its bootloader, and
closing it drops DTR again. So every new connection gets the same reset
a local `serial.Serial(...)` would have given it, which is exactly what
avrdude needs and what the tools expect. Holding the port open across
connections would work for the tools and quietly fail for flashing.

One client at a time, because a serial port has one owner. A second
connection is told so and dropped rather than being interleaved with the
first, which would corrupt both.

The port is bound on the LAN, like the head's own UDP socket. Anything
that can reach it can drive the console's controller port, so it belongs
on a bench network and not on a hostile one.
"""
import argparse
import errno
import os
import select
import socket
import sys
import termios
import time


def open_serial(path, baud):
    """The port in raw mode at the given baud. Opening asserts DTR, which
    is the Uno's reset."""
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        speed = getattr(termios, f"B{baud}")
    except AttributeError:
        os.close(fd)
        raise SystemExit(f"baud {baud} is not one termios knows")
    a = termios.tcgetattr(fd)
    a[0] = termios.IGNPAR                                     # iflag
    a[1] = 0                                                  # oflag
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | termios.HUPCL  # cflag
    a[3] = 0                                                  # lflag: raw
    a[4] = speed                                              # ispeed
    a[5] = speed                                              # ospeed
    a[6] = list(a[6])
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def relay(conn, fd, log):
    """Bytes both ways until either end closes."""
    conn.setblocking(False)
    os.set_blocking(fd, False)
    to_port, to_net = b"", b""
    while True:
        want_w = ([conn] if to_net else []) + ([fd] if to_port else [])
        r, w, x = select.select([conn, fd], want_w, [conn, fd], 1.0)
        if x:
            return "the link reported an error"
        if conn in r:
            try:
                d = conn.recv(4096)
            except (BlockingIOError, InterruptedError):
                d = b""
            except OSError as e:
                return f"the client went away ({errno.errorcode.get(e.errno, e.errno)})"
            if d == b"" and not isinstance(d, type(None)):
                try:
                    if conn.recv(1, socket.MSG_PEEK) == b"":
                        return "the client closed"
                except BlockingIOError:
                    pass
                except OSError:
                    return "the client closed"
            to_port += d
        if fd in r:
            try:
                d = os.read(fd, 4096)
            except (BlockingIOError, InterruptedError):
                d = b""
            except OSError as e:
                return f"the serial port went away ({errno.errorcode.get(e.errno, e.errno)})"
            to_net += d
        if to_port and fd in w:
            n = os.write(fd, to_port)
            to_port = to_port[n:]
        if to_net and conn in w:
            try:
                n = conn.send(to_net)
            except OSError:
                return "the client closed while being written to"
            to_net = to_net[n:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--listen", default="0.0.0.0:6545")
    a = ap.parse_args()
    host, _, p = a.listen.rpartition(":")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host or "0.0.0.0", int(p)))
    srv.listen(4)

    def log(s):
        print(f"{time.strftime('%H:%M:%S')} {s}", flush=True)

    log(f"serial-bridge: {a.port} at {a.baud} on {a.listen}; the port opens per connection, so each one resets the board")
    busy = None
    while True:
        conn, who = srv.accept()
        if busy:
            conn.sendall(b"# serial-bridge: busy, one client at a time\n")
            conn.close()
            log(f"refused {who[0]}:{who[1]}: already serving")
            continue
        busy = who
        log(f"open for {who[0]}:{who[1]}")
        fd = None
        try:
            fd = open_serial(a.port, a.baud)
            why = relay(conn, fd, log)
            log(f"closed for {who[0]}:{who[1]}: {why}")
        except Exception as e:  # noqa: BLE001
            log(f"error for {who[0]}:{who[1]}: {e}")
            try:
                conn.sendall(f"# serial-bridge: {e}\n".encode())
            except OSError:
                pass
        finally:
            if fd is not None:
                os.close(fd)
            conn.close()
            busy = None


if __name__ == "__main__":
    sys.exit(main())
