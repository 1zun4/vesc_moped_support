#!/usr/bin/env python3
"""
Definitive, in-band transmit test using the dashboard as a witness.

The dashboard ACKs ( `68 10 ef 68 84 ...` ) every checksum-valid `10EF 04` frame
it receives. So: wait for the ECU's display push + its ACK (bus now idle), inject
OUR OWN valid `10EF 04`, then listen ~50ms. If a SECOND `10EF 84` ACK appears,
the dashboard received our frame -> our transmit physically reaches the bus.

No disconnecting, non-disruptive (valid frame in the idle window). Keep the
scooter on with the real controller connected.
"""
import sys
import time

import serial

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame  # noqa: E402

PORT, BAUD = "/dev/ttyUSB0", 9600
TEMPLATE = [0x80, 0x50, 0x01, 0x00, 0xAA, 0x23, 0, 0, 0, 0, 0, 0, 0x0E, 0x1F, 0xBF]
ACK = bytes.fromhex("6810ef6884")        # dashboard ACK signature


def myframe():
    wire = bytes((b + 0x33) & 0xFF for b in TEMPLATE)
    return build_frame(0x10, 0xEF, 0x04, wire, preamble=4)


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0)
    try:
        import fcntl, array
        ssr = array.array('i', [0] * 64)
        fcntl.ioctl(ser.fd, 0x541E, ssr, True); ssr[4] |= (1 << 13)
        fcntl.ioctl(ser.fd, 0x541F, ssr)
    except Exception:
        pass

    frame = myframe()
    print(f"# TX-confirm. Injecting {frame.hex(' ')}")
    print("# watching for the dashboard to ACK OUR frame (proves TX reaches the bus)\n")
    buf = bytearray()
    sent = acked = 0
    armed = True
    last = -1.0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 20:
        now = time.perf_counter()
        n = ser.in_waiting
        if n:
            buf.extend(ser.read(n))
            if len(buf) > 200:
                del buf[:-200]
        # fire in the idle gap AFTER the ECU's dash-ACK fully finishes.
        # (Detecting the ACK *prefix* means the dash is still sending 01 34 88 16,
        #  so wait ~15ms for it to finish + the bus to settle before transmitting.)
        if armed and (now - last) > 0.15 and buf.endswith(ACK):
            time.sleep(0.015)
            ser.reset_input_buffer()           # drop the ACK tail; isolate OUR reply
            ser.write(frame); ser.flush()      # CH340E TNOW handles direction
            sent += 1
            last = now; armed = False
            # listen for the dashboard's ACK to OUR frame
            resp = bytearray()
            tw = time.perf_counter()
            while time.perf_counter() - tw < 0.06:
                m = ser.in_waiting
                if m:
                    resp.extend(ser.read(m))
                time.sleep(0.001)
            if ACK in bytes(resp):
                acked += 1
            print(f"  sent #{sent}: {'ACKed by dash ✅' if ACK in bytes(resp) else 'no ACK'}"
                  f"   (resp {bytes(resp).hex(' ')[:40] or 'silent'})")
        elif not armed and (now - last) > 0.15:
            armed = True; buf.clear(); ser.reset_input_buffer()
        else:
            time.sleep(0.0005)
    ser.close()
    print(f"\n# RESULT: injected {sent} frames, dashboard ACKed {acked}.")
    if acked > 0:
        print("#  -> TX PHYSICALLY REACHES THE BUS (dashboard responded to our frame).")
        print("#     The injection problem is timing/content/forwarding, not hardware.")
    else:
        print("#  -> dashboard never ACKed us: our transmit is NOT reaching the bus.")


if __name__ == "__main__":
    main()
