#!/usr/bin/env python3
"""
NIU N1S slave simulator: impersonate the motor controller (node 0x20) and the
battery/BMS (node 0x31) on the live RS485 bus.

The real ECU stays the bus master and the real dashboard stays the display. The
ECU polls 0x20 and 0x31 (both physically absent), waits ~30 ms for a reply with
the bus idle, then forwards what it gets to the screen. We answer those polls
with fabricated telemetry, so the dashboard shows OUR battery % and speed -- with
no bus collisions (we only ever transmit in the idle reply window).

We never touch the 0x10 display frame (that's the ECU->dashboard channel).

Reply formats:
  battery (0x31 cmd02 'pack data'): exact niu-bms-readout layout -- SoC at payload
    offset 6 (byte-0x33), voltage 0-1, current 2-3, temps 9-12 (all +0x33 / +0x3333).
  controller (0x20 cmd02): the real 12-byte response template captured live; the
    speed byte is unknown until mapped on the display (use --ctrl-probe).

DEFAULT IS DRY-RUN (prints the responses it *would* send). Pass --transmit to go live.

Modes:
  run                 answer battery (SoC=--soc) and controller (template, optional
                      speed animation at --speed-pos) -- the deliverable
  --batt-only         answer only the BMS poll (isolate the battery test)
  --ctrl-probe POS    answer controller poll with byte POS cycling --values, so you
                      can see which display element (speed?) it drives
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame  # noqa: E402

DEFAULT_PORT = "/dev/ttyUSB0"
BAUD = 9600

# Exact ECU poll frames (no FE preamble) -- we fire when the RX buffer ends with one.
POLL_BMS2 = bytes.fromhex("6831ce680202604275" + "16")   # battery pack-data
POLL_CTRL2 = bytes.fromhex("6820df680202383b46" + "16")  # controller status
POLL_CTRL6 = bytes.fromhex("6820df68060144" + "1a16")    # controller cmd06

# Real 12-byte controller cmd02 response payload (on-wire), captured live.
CTRL_TEMPLATE = bytearray.fromhex("6f678d3433" "5e" "33333333" "bbb3")


def enc16(value):
    """Encode a decoded 16-bit field: on-wire u16 = value + 0x3333, big-endian."""
    u = (value + 0x3333) & 0xFFFF
    return bytes([u >> 8, u & 0xFF])


def b1(value):
    """Encode a decoded single byte: on-wire = value + 0x33."""
    return (value + 0x33) & 0xFF


def battery_frame(soc, volt=50.5, current=0.0, temp=24, time_remain=99):
    """0x31 cmd02 'pack data' response. SoC drives the dashboard battery gauge."""
    p = bytearray(15)
    p[0:2] = enc16(int(round(volt * 10)))      # pack voltage  (V*10)
    p[2:4] = enc16(int(round(current * 10)))   # pack current  (A*10), 0 = idle
    p[4] = b1(0)
    p[5] = b1(0)
    p[6] = b1(soc)                              # <-- SoC %
    p[7] = b1(0)
    p[8] = b1(min(time_remain, 0xFF - 0x33))   # time remaining (*10 on decode)
    p[9] = p[10] = p[11] = p[12] = b1(temp)    # 4 temperature sensors, degC
    p[13] = b1(0)
    p[14] = b1(0)
    return build_frame(0x31, 0xCE, 0x82, bytes(p), preamble=0)


def ctrl2_frame(overrides=None):
    """0x20 cmd02 response. overrides: {pos: decoded_value}."""
    p = bytearray(CTRL_TEMPLATE)
    for pos, val in (overrides or {}).items():
        p[pos] = b1(val)
    return build_frame(0x20, 0xDF, 0x82, bytes(p), preamble=0)


def ctrl6_frame():
    """Minimal 0x20 cmd06 ack (format unknown; empty payload guess)."""
    return build_frame(0x20, 0xDF, 0x86, b"", preamble=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--transmit", action="store_true", help="actually answer on the bus")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--soc", type=int, default=67, help="battery %% to report")
    ap.add_argument("--volt", type=float, default=50.5)
    ap.add_argument("--temp", type=int, default=24)
    ap.add_argument("--batt-only", action="store_true")
    ap.add_argument("--ctrl-probe", type=int, default=None,
                    help="controller payload position to cycle (map speed)")
    ap.add_argument("--values", default="0,25,50,75,99")
    ap.add_argument("--hold", type=float, default=2.5, help="probe seconds per value")
    ap.add_argument("--speed-pos", type=int, default=None,
                    help="controller pos that is speed; animate 0->99->0 there")
    ap.add_argument("--speed-max", type=int, default=99)
    ap.add_argument("--speed-secs", type=float, default=6.0, help="0->max sweep time")
    ap.add_argument("--ctrl-set", action="append", help="hold controller pos=val (decoded)")
    ap.add_argument("--ctrl06", action="store_true", help="also ack controller cmd06")
    args = ap.parse_args()

    base_over = {}
    for s in args.ctrl_set or []:
        pos, val = s.split("=")
        base_over[int(pos)] = int(val, 0)
    probe_vals = [int(v, 0) for v in args.values.split(",")]

    def ctrl_response(t):
        over = dict(base_over)
        if args.ctrl_probe is not None:
            over[args.ctrl_probe] = probe_vals[int(t / args.hold) % len(probe_vals)]
        elif args.speed_pos is not None:
            # triangle 0 -> max -> 0
            ph = (t % (2 * args.speed_secs)) / args.speed_secs
            spd = ph * args.speed_max if ph <= 1 else (2 - ph) * args.speed_max
            over[args.speed_pos] = int(spd)
        return ctrl2_frame(over)

    ser = None
    if args.transmit:
        import serial
        ser = serial.Serial(args.port, BAUD, timeout=0)

    counts = {"bms2": 0, "ctrl2": 0, "ctrl6": 0}
    buf = bytearray()
    t0 = time.perf_counter()
    last_report = t0
    print(f"# simulate: SoC={args.soc}%, "
          f"{'probe pos %d' % args.ctrl_probe if args.ctrl_probe is not None else ('speed pos %s' % args.speed_pos)}, "
          f"{'TRANSMIT' if ser else 'DRY-RUN'}; Ctrl-C to stop")

    def emit(name, frame, info=""):
        counts[name] += 1
        if ser:
            ser.write(frame)
            ser.flush()
        else:
            print(f"DRY {name}: {frame.hex(' ')}  {info}")

    try:
        while args.seconds is None or time.perf_counter() - t0 < args.seconds:
            t = time.perf_counter() - t0
            if ser:
                n = ser.in_waiting
                if n:
                    buf.extend(ser.read(n))
                    if len(buf) > 64:
                        del buf[:-64]
                    if buf.endswith(POLL_BMS2):
                        emit("bms2", battery_frame(args.soc, args.volt, temp=args.temp))
                        buf.clear()
                    elif not args.batt_only and buf.endswith(POLL_CTRL2):
                        emit("ctrl2", ctrl_response(t))
                        buf.clear()
                    elif not args.batt_only and args.ctrl06 and buf.endswith(POLL_CTRL6):
                        emit("ctrl6", ctrl6_frame())
                        buf.clear()
                else:
                    time.sleep(0.0005)
            else:
                # dry-run: show what we'd answer, once per second
                emit("bms2", battery_frame(args.soc, args.volt, temp=args.temp), f"soc={args.soc}")
                if not args.batt_only:
                    emit("ctrl2", ctrl_response(t), f"t={t:.1f}")
                time.sleep(1.0)
            if ser and time.perf_counter() - last_report > 3.0:
                last_report = time.perf_counter()
                print(f"  t={t:5.1f}s  polls answered: BMS={counts['bms2']} "
                      f"CTRL={counts['ctrl2']} CTRL6={counts['ctrl6']}")
    except KeyboardInterrupt:
        pass
    finally:
        if ser:
            ser.close()
    print(f"# done. answered BMS={counts['bms2']} CTRL={counts['ctrl2']} CTRL6={counts['ctrl6']}")


if __name__ == "__main__":
    main()
