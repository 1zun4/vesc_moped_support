#!/usr/bin/env python3
"""
Timeline analyser for a calibration capture.

Reads a timestamped capture (.jsonl from sniff.py) and reconstructs, per message
type (addr,cmd), how each DECODED payload byte changes over time. The point is to
correlate byte changes with the human actions performed during capture (ignition
on, mode change, motor spin -> km/h, READY toggle), so we can map which byte is
speed, which is a mode/READY flag, and to capture the start-up handshake.

Outputs:
  1. message types with first/last-seen times  (catches start-up-only frames)
  2. any cmd 0x01 handshake frames + responses  (the controller init we need)
  3. per-type: which payload positions are CONSTANT vs CHANGING
  4. a merged, time-sorted list of every byte-change event (the correlation aid)

Usage: timeline.py captures/calib.jsonl [--addr 20DF] [--since 0] [--until 1e9]
"""
import argparse
import json
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import parse_stream, decode_payload  # noqa: E402


def load_timed_frames(jsonl_path):
    """Rebuild the byte stream with per-byte timestamps, parse frames, and tag
    each frame with the arrival time of its first byte."""
    times, raw = [], bytearray()
    for line in open(jsonl_path):
        e = json.loads(line)
        b = bytes.fromhex(e["hex"])
        for x in b:
            times.append(e["t"])
            raw.append(x)
    raw = bytes(raw)
    frames = parse_stream(raw)
    out, pos = [], 0
    for f in frames:
        i = raw.find(f["raw"], pos)
        if i < 0:
            i = raw.find(f["raw"])
        pos = i + len(f["raw"])
        f["t"] = times[i] if i < len(times) else (times[-1] if times else 0)
        out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--addr", help="hex filter e.g. 20DF or 10EF (else all)")
    ap.add_argument("--since", type=float, default=0.0)
    ap.add_argument("--until", type=float, default=1e9)
    ap.add_argument("--min-changes", type=int, default=1)
    args = ap.parse_args()

    frames = [f for f in load_timed_frames(args.jsonl)
              if args.since <= f["t"] <= args.until]
    if args.addr:
        a = int(args.addr, 16)
        frames = [f for f in frames if f["addr"] == a]
    if not frames:
        print("no frames")
        return
    t0 = frames[0]["t"]

    # 1. message types, first/last seen
    seen = {}
    for f in frames:
        k = (f["addr"], f["cmd"], f["len"])
        if k not in seen:
            seen[k] = [f["t"], f["t"], 0]
        seen[k][1] = f["t"]
        seen[k][2] += 1
    print("# message types (addr cmd len : first..last s, count):")
    for (a, c, ln), (t1, t2, n) in sorted(seen.items()):
        d = "RESP" if c & 0x80 else "REQ "
        flag = "  <-- transient/startup" if (t2 - t1) < 3 and n < 6 else ""
        print(f"  {a:04X} {c:02X} {ln:>2} {d}: {t1-t0:6.1f}..{t2-t0:6.1f}  x{n}{flag}")

    # 2. handshake: any cmd with low bits 0x01, plus its neighbours
    print("\n# cmd 0x01 / handshake frames (first 12):")
    hs = [f for f in frames if (f["cmd"] & 0x7F) == 0x01]
    for f in hs[:12]:
        print(f"  t={f['t']-t0:6.1f} {f['raw'].hex(' ')}")
    if not hs:
        print("  (none seen)")

    # 3 & 4. per-type changing bytes + merged change events
    events = []  # (t, addr, cmd, pos, old, new)
    by_type = defaultdict(list)  # (addr,cmd) -> [(t, decoded bytes)]
    for f in frames:
        by_type[(f["addr"], f["cmd"])].append((f["t"], decode_payload(f["payload"])))

    print("\n# per-type payload byte stability (C=const, digits=#distinct values):")
    for (a, c), seq in sorted(by_type.items()):
        if not seq or not seq[0][1]:
            continue
        ln = len(seq[0][1])
        prof = []
        for p in range(ln):
            vals = {pl[p] for _, pl in seq if len(pl) > p}
            prof.append("C" if len(vals) == 1 else (str(len(vals)) if len(vals) < 10 else "*"))
        print(f"  {a:04X} {c:02X}: [{' '.join(prof)}]")
        # collect change events per position
        for p in range(ln):
            last = None
            for t, pl in seq:
                if len(pl) <= p:
                    continue
                v = pl[p]
                if last is not None and v != last:
                    events.append((t, a, c, p, last, v))
                last = v

    events.sort()
    print(f"\n# byte-change timeline ({len(events)} events) "
          f"-- correlate with your actions:")
    for t, a, c, p, old, new in events:
        print(f"  t={t-t0:7.2f}  {a:04X} {c:02X} pos{p:<2} {old:02X} -> {new:02X}"
              f"   (dec {old}->{new})")


if __name__ == "__main__":
    main()
