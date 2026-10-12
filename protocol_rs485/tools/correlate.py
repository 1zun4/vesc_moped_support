#!/usr/bin/env python3
"""
Diagnostic: do our faked controller/battery replies actually reach the display?

We respond to the ECU's polls of 0x20 (controller) and 0x31 (battery) while
ALTERNATING the injected battery SoC between two values every few seconds. At the
same time we watch the ECU->dashboard 10EF 04 display frame. If any display-frame
byte tracks the injected SoC, the ECU forwards battery data to the screen (and we
learn which byte). If nothing tracks it, the ECU isn't accepting/forwarding our
replies -- a different mechanism is needed.

We also tally EVERY poll command the ECU sends, to catch a controller init/
handshake (e.g. cmd 0x01) that may gate everything.

Always transmits (this is a live experiment). Ctrl-C or --seconds to stop.
"""
import argparse
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import parse_stream, decode_payload                       # noqa: E402
from simulate import (POLL_BMS2, POLL_CTRL2, POLL_CTRL6,             # noqa: E402
                      battery_frame, ctrl2_frame, ctrl6_frame)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--soc-a", type=int, default=67)
    ap.add_argument("--soc-b", type=int, default=15)
    ap.add_argument("--swap", type=float, default=6.0, help="seconds per SoC value")
    args = ap.parse_args()

    import serial
    ser = serial.Serial(args.port, 9600, timeout=0)

    buf = bytearray()       # poll detection (cleared on match)
    watch = bytearray()     # frame watching
    poll_cmds = Counter()   # every REQ (addr,cmd) seen
    answered = Counter()
    # display-frame decoded payload samples, grouped by injected SoC
    disp_by_soc = defaultdict(Counter)

    t0 = time.perf_counter()
    last_parse = t0

    # Phase A: normal (battery=soc_a, controller=template).
    # Phase B: marked  (battery=soc_b, controller payload = distinctive 0x40+i ramp).
    MARK = {i: 0x40 + i for i in range(12)}   # decoded controller bytes -> 40..4B

    def phase_now(t):
        return "A" if int(t / args.swap) % 2 == 0 else "B"

    print(f"# correlate: A(batt={args.soc_a},ctrl=template) <-> "
          f"B(batt={args.soc_b},ctrl=MARKED 40..4B) every {args.swap}s, {args.seconds}s.")
    try:
        while time.perf_counter() - t0 < args.seconds:
            now = time.perf_counter()
            ph = phase_now(now - t0)
            soc = args.soc_a if ph == "A" else args.soc_b
            ctrl = ctrl2_frame() if ph == "A" else ctrl2_frame(MARK)
            n = ser.in_waiting
            if n:
                data = ser.read(n)
                buf.extend(data)
                watch.extend(data)
                if len(buf) > 64:
                    del buf[:-64]
                if buf.endswith(POLL_BMS2):
                    ser.write(battery_frame(soc)); ser.flush()
                    answered["bms"] += 1
                    buf.clear()
                elif buf.endswith(POLL_CTRL2):
                    ser.write(ctrl); ser.flush()
                    answered["ctrl2"] += 1
                    buf.clear()
                elif buf.endswith(POLL_CTRL6):
                    ser.write(ctrl6_frame()); ser.flush()
                    answered["ctrl6"] += 1
                    buf.clear()
            else:
                time.sleep(0.0005)
            if now - last_parse > 0.25 and watch:
                last_parse = now
                for f in parse_stream(bytes(watch)):
                    if not (f["cmd"] & 0x80):
                        poll_cmds[(f["addr"], f["cmd"])] += 1
                    if f["addr"] == 0x10EF and f["cmd"] == 0x04:
                        dec = decode_payload(f["payload"]).hex(" ")
                        disp_by_soc[ph][dec] += 1
                del watch[:-40]
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

    print("\n# poll commands the ECU sent (addr cmd : count):")
    for (a, c), n in sorted(poll_cmds.items()):
        print(f"    {a:04X} {c:02X} : {n}")
    print(f"# we answered: {dict(answered)}")

    print("\n# 10EF 04 display-frame decoded payloads, grouped by phase:")
    for ph in ("A", "B"):
        print(f"  Phase {ph} ({'normal' if ph=='A' else 'MARKED'}):")
        for dec, n in disp_by_soc.get(ph, Counter()).most_common(5):
            print(f"      x{n:<3} {dec}")
    # union of all display bytes seen in phase B -> look for our markers 0x40..0x4B
    mark_hits = set()
    for dec in disp_by_soc.get("B", Counter()):
        for i, byte in enumerate(dec.split()):
            if 0x40 <= int(byte, 16) <= 0x4B:
                mark_hits.add((i, byte))
    print("\n# our controller markers (0x40..0x4B) appearing in the display frame:")
    print(f"    {sorted(mark_hits) if mark_hits else 'NONE'}")
    # positions whose value-set differs between phase A and B
    posvals = {"A": defaultdict(set), "B": defaultdict(set)}
    for ph in ("A", "B"):
        for dec in disp_by_soc.get(ph, Counter()):
            for i, byte in enumerate(dec.split()):
                posvals[ph][i].add(byte)
    npos = max([len(d.split()) for ph in ("A", "B") for d in disp_by_soc.get(ph, {})] or [0])
    differ = [i for i in range(npos)
              if posvals["A"][i] and posvals["B"][i] and posvals["A"][i] != posvals["B"][i]]
    print(f"\n# display positions whose values differ A-vs-B: {differ}")
    for i in differ:
        print(f"    pos {i}: A={sorted(posvals['A'][i])}  B={sorted(posvals['B'][i])}")
    if not mark_hits and not differ:
        print("\n# CONCLUSION: neither faked controller NOR battery reaches the display.")


if __name__ == "__main__":
    main()
