#!/usr/bin/env python3
"""
Serial sniffer for the NIU N1S RS485 bus (CH340 adapter on /dev/ttyUSB0).

Passive listener only -- it never transmits. Two modes:

  sweep   : try a list of baud rates, capture a short window at each, and
            score how "frame-like" the resulting byte stream looks. Used to
            discover the unknown line rate.

  capture : open one baud rate and record a longer window with arrival
            timestamps. Saves a raw .bin plus a timestamped .jsonl event log
            and prints a hexdump + gap-based frame segmentation.

Nothing here is NIU-specific yet; it is a generic UART recon tool.
"""
import argparse
import json
import math
import sys
import time
from collections import Counter

import serial  # pyserial, from .venv

DEFAULT_PORT = "/dev/ttyUSB0"
# Standard rates most likely for a vehicle/BMS RS485 bus, low->high.
SWEEP_BAUDS = [2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400]


def entropy(counts):
    """Shannon entropy in bits/byte of a Counter of byte values."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        h -= p * math.log2(p)
    return h


def longest_period(data, max_period=64):
    """Crude periodicity detector: find the stride (1..max_period) that
    maximizes self-match fraction. Strong periodicity => regular framing."""
    n = len(data)
    if n < 8:
        return (0, 0.0)
    best = (0, 0.0)
    for p in range(1, min(max_period, n // 2) + 1):
        matches = sum(1 for i in range(n - p) if data[i] == data[i + p])
        frac = matches / (n - p)
        if frac > best[1]:
            best = (p, frac)
    return best


def score_window(data):
    """Heuristic score: structured-but-not-empty streams score high.
    Returns (score, metrics dict)."""
    n = len(data)
    if n == 0:
        return (0.0, {"bytes": 0})
    counts = Counter(data)
    h = entropy(counts)
    distinct = len(counts)
    zero_frac = counts.get(0x00, 0) / n
    ff_frac = counts.get(0xFF, 0) / n
    period, period_frac = longest_period(data, 64)
    # A real, correctly-clocked frame stream tends to:
    #  - have moderate entropy (not ~0 = stuck line, not ~8 = pure noise)
    #  - not be dominated by 0x00/0xFF (those scream wrong-baud / idle noise)
    #  - show periodicity (repeating frame structure)
    mid_entropy = 1.0 - abs(h - 4.0) / 4.0          # peaks at 4 bits/byte
    not_stuck = 1.0 - max(zero_frac, ff_frac)
    structured = period_frac
    score = n and (0.4 * structured + 0.35 * not_stuck + 0.25 * max(mid_entropy, 0))
    metrics = {
        "bytes": n,
        "entropy_bits": round(h, 2),
        "distinct": distinct,
        "zero_frac": round(zero_frac, 3),
        "ff_frac": round(ff_frac, 3),
        "period": period,
        "period_frac": round(period_frac, 3),
        "top": [(f"{b:02X}", c) for b, c in counts.most_common(6)],
    }
    return (round(score, 4), metrics)


def hexdump(data, limit=256):
    out = []
    data = data[:limit]
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        asci = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"  {off:04X}  {hexs:<47}  {asci}")
    return "\n".join(out)


def read_window(port, baud, seconds):
    """Open port at baud, flush, read for `seconds`, return raw bytes."""
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = 0.05
    ser.rtscts = False
    ser.dsrdtr = False
    ser.open()
    try:
        time.sleep(0.15)
        ser.reset_input_buffer()
        buf = bytearray()
        t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end:
            n = ser.in_waiting
            if n:
                buf.extend(ser.read(n))
            else:
                time.sleep(0.005)
        return bytes(buf)
    finally:
        ser.close()


def cmd_sweep(args):
    print(f"# Baud sweep on {args.port}, {args.seconds}s per rate\n")
    results = []
    for baud in args.bauds:
        try:
            data = read_window(args.port, baud, args.seconds)
        except Exception as e:
            print(f"baud {baud:>7}: ERROR {e}")
            continue
        score, m = score_window(data)
        results.append((score, baud, m, data))
        rate = m["bytes"] / args.seconds
        print(f"baud {baud:>7}: score={score:<6} {m['bytes']:>5}B "
              f"({rate:6.0f} B/s) H={m['entropy_bits']:<4} "
              f"distinct={m['distinct']:<3} 00={m['zero_frac']} FF={m['ff_frac']} "
              f"period={m['period']}@{m['period_frac']} top={m['top']}")
    if not results:
        print("\nNo data captured at any baud. Is the bus powered / is anything "
              "transmitting? RS485 is half-duplex; a master may need to poll.")
        return
    results.sort(reverse=True)
    print("\n# Ranked (best first):")
    for score, baud, m, _ in results:
        print(f"  {baud:>7}  score={score}  bytes={m['bytes']}")
    best_score, best_baud, _, best_data = results[0]
    print(f"\n# Best candidate: {best_baud} baud (score {best_score})")
    if best_data:
        print(hexdump(best_data, 256))


def cmd_capture(args):
    ser = serial.Serial()
    ser.port = args.port
    ser.baudrate = args.baud
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = 0.02
    ser.open()
    time.sleep(0.1)
    ser.reset_input_buffer()

    raw = bytearray()
    events = []  # (t_rel, hexchunk)
    gap_thresh = args.gap / 1000.0  # ms -> s
    print(f"# Capturing {args.seconds}s at {args.baud} baud on {args.port} "
          f"(gap frame split @ {args.gap}ms)")
    t0 = time.perf_counter()
    t_last = t0
    t_end = t0 + args.seconds
    try:
        while time.perf_counter() < t_end:
            n = ser.in_waiting
            if n:
                chunk = ser.read(n)
                now = time.perf_counter()
                raw.extend(chunk)
                events.append((round(now - t0, 6), chunk.hex()))
                t_last = now
            else:
                time.sleep(0.002)
    finally:
        ser.close()

    base = args.out
    with open(base + ".bin", "wb") as f:
        f.write(raw)
    with open(base + ".jsonl", "w") as f:
        for t, h in events:
            f.write(json.dumps({"t": t, "hex": h}) + "\n")
    print(f"# Wrote {len(raw)} bytes -> {base}.bin , {len(events)} chunks -> {base}.jsonl")

    # Gap-based frame segmentation from chunk arrival times.
    frames = []
    cur = bytearray()
    last_t = None
    for t, h in events:
        b = bytes.fromhex(h)
        if last_t is not None and (t - last_t) > gap_thresh and cur:
            frames.append(bytes(cur))
            cur = bytearray()
        cur.extend(b)
        last_t = t
    if cur:
        frames.append(bytes(cur))

    print(f"\n# {len(frames)} gap-delimited frame(s):")
    flens = Counter(len(fr) for fr in frames)
    print(f"# frame-length histogram: {dict(sorted(flens.items()))}")
    for i, fr in enumerate(frames[:args.show]):
        print(f"\n[{i}] len={len(fr)}")
        print(hexdump(fr, 64))
    print("\n# Full hexdump (first 512B):")
    print(hexdump(bytes(raw), 512))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sweep", help="discover baud rate")
    sp.add_argument("--port", default=DEFAULT_PORT)
    sp.add_argument("--seconds", type=float, default=2.5)
    sp.add_argument("--bauds", type=int, nargs="+", default=SWEEP_BAUDS)
    sp.set_defaults(func=cmd_sweep)

    cp = sub.add_parser("capture", help="timestamped deep capture")
    cp.add_argument("--port", default=DEFAULT_PORT)
    cp.add_argument("--baud", type=int, required=True)
    cp.add_argument("--seconds", type=float, default=10.0)
    cp.add_argument("--gap", type=float, default=10.0, help="frame gap split, ms")
    cp.add_argument("--out", default="capture")
    cp.add_argument("--show", type=int, default=12, help="frames to hexdump")
    cp.set_defaults(func=cmd_capture)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
