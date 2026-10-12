#!/usr/bin/env python3
"""
Display-frame override (improved): clone the ECU's LIVE 10EF 04 frame, change only
the speed byte (decoded pos 3), pad the tail, and inject in the post-ACK idle gap.

Addresses the remaining transmit hypotheses:
  - clone live frame  -> heartbeat/sequence bytes (pos 0/1/14) match the ECU's
                         current value, so a sequence-checking dashboard accepts it.
  - tail padding      -> protects the real 0x16 EOF from CH340E TNOW turn-off truncation.
  - fire 15ms after the dash ACK -> no collision with the ACK tail.

If the speedometer moves, transmit works. CH340E TNOW handles direction (rts=auto).
"""
import argparse
import sys
import time

import serial

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame, parse_stream, decode_payload  # noqa: E402

PORT, BAUD = "/dev/ttyUSB0", 9600
ACK = bytes.fromhex("6810ef6884")
TEMPLATE = [0x80, 0x50, 0x01, 0x00, 0xAA, 0x23, 0, 0, 0, 0, 0, 0, 0x0E, 0x1F, 0xBF]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--sweep-secs", type=float, default=5.0)
    ap.add_argument("--max", type=int, default=99)
    ap.add_argument("--speed-pos", type=int, default=3)
    ap.add_argument("--pad", type=int, default=3, help="tail padding bytes")
    ap.add_argument("--fixed", type=int, default=None, help="hold a fixed speed instead of sweeping")
    args = ap.parse_args()

    ser = serial.Serial(PORT, BAUD, timeout=0)
    try:
        import fcntl, array
        ss = array.array('i', [0] * 64)
        fcntl.ioctl(ser.fd, 0x541E, ss, True); ss[4] |= (1 << 13)
        fcntl.ioctl(ser.fd, 0x541F, ss)
    except Exception:
        pass

    latest = list(TEMPLATE)
    have_live = False

    def make(spd):
        d = list(latest)
        d[args.speed_pos] = spd & 0xFF
        wire = bytes((b + 0x33) & 0xFF for b in d)
        return build_frame(0x10, 0xEF, 0x04, wire, preamble=4) + bytes([0xFF]) * args.pad

    def speed(t):
        if args.fixed is not None:
            return args.fixed
        ph = (t % (2 * args.sweep_secs)) / args.sweep_secs
        return int(ph * args.max if ph <= 1 else (2 - ph) * args.max)

    buf = bytearray()
    watch = bytearray()
    fired = 0
    armed = True
    last_tx = -1.0
    t0 = time.perf_counter()
    last_report = last_parse = t0
    print(f"# override (clone live frame + pad {args.pad}). Watch speedometer "
          f"({'fixed ' + str(args.fixed) if args.fixed is not None else '0->%d sweep' % args.max}).")
    while time.perf_counter() - t0 < args.seconds:
        now = time.perf_counter()
        n = ser.in_waiting
        if n:
            data = ser.read(n)
            buf.extend(data); watch.extend(data)
            if len(buf) > 96:
                del buf[:-96]
        # refresh the cloned live ECU frame on a slow timer (cheap; off the hot path)
        if now - last_parse > 0.5 and watch:
            last_parse = now
            for f in parse_stream(bytes(watch)):
                if f["addr"] == 0x10EF and f["cmd"] == 0x04 and f["len"] == 15:
                    latest = list(decode_payload(f["payload"]))
                    have_live = True
            del watch[:-32]
        if armed and (now - last_tx) > 0.15 and ACK in buf:
            time.sleep(0.015)
            ser.reset_input_buffer()
            ser.write(make(speed(now - t0))); ser.flush()
            fired += 1; last_tx = now; armed = False
            buf.clear()
        elif not armed and (now - last_tx) > 0.15:
            armed = True; buf.clear(); ser.reset_input_buffer()
        else:
            time.sleep(0.0005)
        if now - last_report > 3.0:
            last_report = now
            print(f"  t={now-t0:4.1f}s sent={fired} live_frame={'yes' if have_live else 'no'} "
                  f"inject_speed={speed(now-t0)} cloned={[hex(x) for x in latest[:4]]}")
    ser.close()
    print(f"# done, sent {fired} frames (cloned live ECU frame={have_live})")


if __name__ == "__main__":
    main()
