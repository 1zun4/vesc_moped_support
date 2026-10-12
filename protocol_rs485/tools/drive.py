#!/usr/bin/env python3
"""
Controller emulator / dashboard driver for the NIU N1S.

The dashboard (node 0x10) renders whatever  68 10 EF 68 04 0F <15B> CS 16  frame
it is fed (confirmed in the gen-2 dashboard firmware: it is a pure slave). This
tool sends that frame with chosen values. Payloads are given in DECODED units;
the tool applies the DL/T-645 +0x33 transmit offset and fixes the checksum.

TWO MODES (the central ECU is the real bus master and stays connected):

  --mode master    : assume WE are the only master; send at a fixed 300ms cadence.
                     Use only if the ECU/other master is removed.

  --mode override  : co-exist with the live ECU master (DEFAULT). We watch the
                     bus; right after the ECU pushes its 10EF 04 and the dash
                     ACKs (10EF 84), the bus is idle for ~60ms, so we slip OUR
                     10EF 04 in. The dash then holds our values until the ECU's
                     next push ~300ms later, when we override again. Last writer
                     wins -> the screen shows our data. We stay out of the ECU's
                     other poll slots, so no collisions.

DEFAULT IS DRY-RUN. Pass --transmit to actually drive the bus.

Subcommands (work in either mode):
  hold     send a fixed frame (template, or --set pos=val overrides)
  probe    cycle ONE payload position through values to see what it controls
  scan     auto-probe every position in turn (field discovery)
  animate  the deliverable: battery=67, speed sweeps 0->99->0, realistic extras
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame, parse_stream  # noqa: E402

DEFAULT_PORT = "/dev/ttyUSB0"
BAUD = 9600
ADDR = 0x10            # dashboard
CMD = 0x04             # display-data command
PERIOD = 0.300         # 300 ms, the master's measured cadence
ACK_SIG = bytes([0x68, 0x10, 0xEF, 0x68, 0x84])   # dash ACK -> end of ECU's push
COOLDOWN = 0.150       # after we fire, ignore ACKs this long (avoid self-retrigger)

# Decoded 15-byte template captured from the real controller (parked scooter).
# +0x33 of this == on-wire b3 c3 34 33 dd 56 33 33 33 33 33 33 40 49 f2.
TEMPLATE = [0x80, 0x90, 0x01, 0x00, 0xAA, 0x23,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0D, 0x16, 0xBF]


def encode(decoded):
    return bytes((v + 0x33) & 0xFF for v in decoded)


def make_frame(decoded, preamble=4):
    return build_frame(ADDR, ADDR ^ 0xFF, CMD, encode(decoded), preamble=preamble)


def open_serial(port):
    import serial
    return serial.Serial(port, BAUD, timeout=0.02)


def run_master(ser, frame_fn, duration, period, quiet):
    """Fixed-cadence send (we are the only master). ser=None => dry-run print."""
    t0 = time.perf_counter()
    i = 0
    acks = 0
    try:
        while duration is None or time.perf_counter() - t0 < duration:
            decoded, note = frame_fn(i, time.perf_counter() - t0)
            fr = make_frame(decoded)
            if ser is None:
                print(f"DRY {fr.hex(' ')}  {note}")
            else:
                ser.reset_input_buffer()
                ser.write(fr); ser.flush()
                time.sleep(0.03)
                resp = ser.read(ser.in_waiting or 1)
                got = parse_stream(resp)
                if got:
                    acks += 1
                if not quiet:
                    print(f"TX {note}  {'ACK' if got else 'ack:-'}")
            i += 1
            nxt = t0 + i * period
            slp = nxt - time.perf_counter()
            if slp > 0:
                time.sleep(slp)
    except KeyboardInterrupt:
        pass
    if ser is not None:
        print(f"# sent {i} frames, {acks} dash ACKs")


def run_override(ser, frame_fn, duration, quiet):
    """Co-master: fire OUR frame right after the dash ACKs the ECU's push."""
    if ser is None:                       # dry-run: just preview at cadence
        run_master(None, frame_fn, duration, PERIOD, quiet)
        return
    t0 = time.perf_counter()
    buf = bytearray()
    last_tx = -1.0
    armed = True
    i = 0
    acks_seen = 0
    try:
        while duration is None or time.perf_counter() - t0 < duration:
            n = ser.in_waiting
            if n:
                buf.extend(ser.read(n))
                if len(buf) > 1024:
                    del buf[:-256]
            now = time.perf_counter()
            if armed and (now - last_tx) > COOLDOWN and ACK_SIG in buf:
                acks_seen += 1
                decoded, note = frame_fn(i, now - t0)
                ser.write(make_frame(decoded)); ser.flush()
                last_tx = now
                armed = False
                i += 1
                buf.clear()
                if not quiet:
                    print(f"OV #{i}  {note}")
            elif not armed and (now - last_tx) > COOLDOWN:
                armed = True
                buf.clear()
                ser.reset_input_buffer()
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    print(f"# fired {i} override frames (synced to ECU cycle)")


def run(args, frame_fn, duration=None, period=PERIOD):
    ser = open_serial(args.port) if args.transmit else None
    try:
        if args.mode == "override":
            run_override(ser, frame_fn, duration, args.quiet)
        else:
            run_master(ser, frame_fn, duration, period, args.quiet)
    finally:
        if ser:
            ser.close()


def parse_sets(decoded, sets):
    for s in sets or []:
        pos, val = s.split("=")
        decoded[int(pos)] = int(val, 0)
    return decoded


def cmd_hold(args):
    decoded = parse_sets(list(TEMPLATE), args.set)
    print(f"# {args.mode}: holding decoded={bytes(decoded).hex(' ')}; Ctrl-C to stop")
    run(args, lambda i, t: (decoded, f"#{i}"), args.seconds)


def cmd_probe(args):
    base = parse_sets(list(TEMPLATE), args.set)
    vals = [int(v, 0) for v in args.values.split(",")]
    print(f"# {args.mode}: PROBE pos {args.pos} cycling {vals} ({args.hold}s each). "
          f"Watch the display; tell me which element changes.")

    def fn(i, t):
        d = list(base)
        d[args.pos] = vals[int(t / args.hold) % len(vals)]
        return d, f"pos{args.pos}={d[args.pos]}"
    run(args, fn, args.seconds)


def cmd_scan(args):
    vals = [int(v, 0) for v in args.values.split(",")]
    positions = (list(range(15)) if not args.only
                 else [int(x) for x in args.only.split(",")])
    print(f"# {args.mode}: SCAN positions {positions} with {vals}, "
          f"{args.hold}s/value, {args.dwell}s/position.")
    for pos in positions:
        print(f"\n>>> POSITION {pos} (template={TEMPLATE[pos]:#04x}) <<<")

        def fn(i, t, pos=pos):
            d = list(TEMPLATE)
            d[pos] = vals[int(t / args.hold) % len(vals)]
            return d, f"pos{pos}={d[pos]}"
        run(args, fn, args.dwell)


def cmd_animate(args):
    span = args.speed_max
    print(f"# {args.mode}: ANIMATE battery[{args.batt_pos}]={args.batt}, "
          f"speed[{args.speed_pos}] 0->{span}->0 @ {args.speed_step}/tick. Ctrl-C to stop.")

    def fn(i, t):
        d = list(TEMPLATE)
        if args.batt_pos >= 0:
            d[args.batt_pos] = args.batt
        phase = (i * args.speed_step) % (2 * span)
        spd = phase if phase <= span else 2 * span - phase
        if args.speed_pos >= 0:
            d[args.speed_pos] = int(spd)
        parse_sets(d, args.set)
        return d, f"spd={int(spd)} batt={args.batt}"
    run(args, fn, args.seconds, period=args.period)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--transmit", action="store_true", help="actually drive the bus")
    ap.add_argument("--mode", choices=["master", "override"], default="override")
    ap.add_argument("--seconds", type=float, default=None, help="duration (default forever)")
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("hold")
    h.add_argument("--set", action="append")
    h.set_defaults(func=cmd_hold)

    p = sub.add_parser("probe")
    p.add_argument("--pos", type=int, required=True)
    p.add_argument("--values", default="0,25,50,75,99")
    p.add_argument("--hold", type=float, default=2.0)
    p.add_argument("--set", action="append")
    p.set_defaults(func=cmd_probe)

    s = sub.add_parser("scan")
    s.add_argument("--values", default="0,99")
    s.add_argument("--hold", type=float, default=1.5)
    s.add_argument("--dwell", type=float, default=6.0)
    s.add_argument("--only")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("animate")
    a.add_argument("--batt", type=int, default=67)
    a.add_argument("--batt-pos", type=int, default=-1)
    a.add_argument("--speed-pos", type=int, default=-1)
    a.add_argument("--speed-max", type=int, default=99)
    a.add_argument("--speed-step", type=int, default=1)
    a.add_argument("--period", type=float, default=PERIOD)
    a.add_argument("--set", action="append")
    a.set_defaults(func=cmd_animate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
