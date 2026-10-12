#!/usr/bin/env python3
"""
Frame builder / replayer for the NIU N1S RS485 protocol.

This is the groundwork for replicating packets. By DEFAULT it only *builds* and
prints frames (dry-run) — it does NOT transmit. Transmitting onto the live bus
requires the explicit --transmit flag, because injecting frames can collide with
the real master and is intended for a later, deliberate phase.

Examples (all dry-run unless --transmit is given):

  # Build one frame and show its bytes
  python tools/replay.py build --addr 0x20 --cmd 0x02 --payload 38,3b

  # Re-emit every frame from a capture (dry-run prints them)
  python tools/replay.py replay --bin captures/long_9600.bin

  # Actually transmit (LATER, deliberate):
  python tools/replay.py build --addr 0x20 --cmd 0x02 --payload 38,3b --transmit
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame, parse_stream  # noqa: E402

DEFAULT_PORT = "/dev/ttyUSB0"
BAUD = 9600


def parse_payload(s):
    if not s:
        return b""
    s = s.replace(",", " ").replace("0x", "").strip()
    return bytes(int(tok, 16) for tok in s.split())


def transmit(frames, port, settle=0.05):
    """Write frames to the bus. Guarded — only called with --transmit.
    The CH340+RS485 module is assumed to auto-toggle the DE/RE direction line
    from the TX data (most do); if yours needs RTS, set rs485 mode here."""
    import serial
    ser = serial.Serial(port, BAUD, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                        timeout=0.2)
    try:
        for fr in frames:
            ser.write(fr)
            ser.flush()
            print(f"TX {fr.hex(' ')}")
            time.sleep(settle)
    finally:
        ser.close()


def cmd_build(args):
    addr = int(str(args.addr), 0)
    cmd = int(str(args.cmd), 0)
    payload = parse_payload(args.payload)
    if args.encode:
        # treat --payload as DECODED/intended values; apply the DL/T-645 +0x33
        # transmit offset to get the on-wire bytes (header/CS/EOF stay plaintext)
        payload = bytes((b + 0x33) & 0xFF for b in payload)
        print(f"# --encode: applied +0x33 -> on-wire payload {payload.hex(' ')}")
    fr = build_frame(addr, addr ^ 0xFF, cmd, payload, preamble=args.preamble)
    print(f"# addr=0x{addr:02X} ~addr=0x{addr ^ 0xFF:02X} cmd=0x{cmd:02X} "
          f"len={len(payload)} preamble={args.preamble}")
    print(fr.hex(" "))
    # self-check: it must parse back to the same fields
    back = parse_stream(fr)
    assert back and back[0]["cs_ok"], "built frame failed self-parse!"
    print(f"# self-check OK (checksum 0x{back[0]['cs']:02X})")
    if args.transmit:
        transmit([fr], args.port)


def cmd_replay(args):
    data = open(args.bin, "rb").read()
    frames = parse_stream(data)
    if args.addr is not None:
        a = int(str(args.addr), 0)
        frames = [f for f in frames if (f["addr"] >> 8) == a]
    raws = [f["raw"] for f in frames][: args.limit]
    print(f"# {len(raws)} frame(s) to replay (dry-run={'no' if args.transmit else 'yes'})")
    for r in raws:
        print(r.hex(" "))
    if args.transmit:
        transmit(raws, args.port)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--transmit", action="store_true",
                    help="ACTUALLY send on the bus (default: dry-run only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build one frame")
    b.add_argument("--addr", required=True, help="node address, e.g. 0x20")
    b.add_argument("--cmd", required=True, help="command byte, e.g. 0x02")
    b.add_argument("--payload", default="", help="hex bytes, e.g. 38,3b")
    b.add_argument("--encode", action="store_true",
                   help="treat --payload as DECODED values; add 0x33 to each byte")
    b.add_argument("--preamble", type=int, default=4, help="leading 0xFE count")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("replay", help="re-emit frames from a capture")
    r.add_argument("--bin", required=True)
    r.add_argument("--addr", default=None, help="filter to one node address")
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_replay)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
