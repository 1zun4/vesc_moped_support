#!/usr/bin/env python3
"""
Structural parser for the NIU N1S RS485 protocol.

Frame grammar (discovered by sniffing, see PROTOCOL.md):

    [FE FE FE FE]?  preamble   (0+ 0xFE bytes, NOT covered by checksum)
    68              SOF
    ADDR_HI ADDR_LO 2-byte node address
    68              header delimiter
    CMD             command byte (bit7 = direction: 0=request, 1=response)
    LEN             payload length N
    PAYLOAD[N]      N bytes
    CS              checksum = sum(bytes from first 0x68 .. last payload) & 0xFF
    16              EOF

This module resync-parses a raw byte stream, validates every checksum, and
prints a catalog of (addr, cmd, len) groups plus per-position field stability.
It is the basis for the later "replicate a packet" work: build_frame() emits a
byte-exact frame and is the inverse of parse_stream().
"""
import argparse
import json
import sys
from collections import Counter, defaultdict

SOF = 0x68
EOF = 0x16
PREAMBLE = 0xFE


def checksum(frame_wo_cs_eof):
    """frame_wo_cs_eof starts at the first 0x68 and ends at last payload byte."""
    return sum(frame_wo_cs_eof) & 0xFF


def decode_payload(payload):
    """NIU/DL/T-645 payloads are transmitted as actual+0x33. Subtract to decode.
    Only the PAYLOAD is offset (not header/checksum/EOF)."""
    return bytes((b - 0x33) & 0xFF for b in payload)


def u16be(decoded, i):
    """Big-endian 16-bit value from already-decoded payload bytes."""
    return (decoded[i] << 8) | decoded[i + 1]


def build_frame(addr_hi, addr_lo, cmd, payload=b"", preamble=4):
    """Inverse of the parser: construct a byte-exact, checksum-correct frame.
    `preamble` = number of leading 0xFE bytes (real bus uses 4 on some frames)."""
    body = bytes([SOF, addr_hi, addr_lo, SOF, cmd, len(payload)]) + bytes(payload)
    cs = checksum(body)
    return bytes([PREAMBLE] * preamble) + body + bytes([cs, EOF])


def parse_stream(data):
    """Yield dict frames from a raw stream, resyncing past noise.
    Each frame: {off, preamble, addr, cmd, len, payload(bytes), cs, cs_ok, raw}."""
    i, n = 0, len(data)
    frames = []
    while i < n:
        if data[i] != SOF:
            i += 1
            continue
        start = i
        # count preceding preamble FEs
        pre = 0
        j = start - 1
        while j >= 0 and data[j] == PREAMBLE:
            pre += 1
            j -= 1
        # need: 68 ADDR ADDR 68 CMD LEN ...
        if i + 5 >= n:
            break
        if data[i + 3] != SOF:
            i += 1
            continue
        addr_hi, addr_lo = data[i + 1], data[i + 2]
        cmd = data[i + 4]
        ln = data[i + 5]
        body_end = i + 6 + ln           # one past last payload byte
        if body_end + 1 >= n:           # need CS + EOF
            break
        cs = data[body_end]
        eof = data[body_end + 1]
        body = data[i:body_end]         # 68 .. last payload
        cs_calc = checksum(body)
        if eof != EOF or cs != cs_calc:
            i += 1                      # false 68, resync
            continue
        frames.append({
            "off": start,
            "preamble": pre,
            "addr": (addr_hi << 8) | addr_lo,
            "cmd": cmd,
            "len": ln,
            "payload": bytes(data[i + 6:body_end]),
            "cs": cs,
            "cs_ok": True,
            "raw": bytes(data[start - pre:body_end + 2]),
        })
        i = body_end + 2
    return frames


def report(data):
    frames = parse_stream(data)
    print(f"# Parsed {len(frames)} valid frames from {len(data)} bytes")
    if not frames:
        return
    ok = sum(f["cs_ok"] for f in frames)
    print(f"# Checksum OK: {ok}/{len(frames)} ({100*ok/len(frames):.1f}%)")

    # coverage: how many bytes are inside valid frames
    covered = sum(len(f["raw"]) for f in frames)
    print(f"# Stream coverage by valid frames: {covered}/{len(data)} "
          f"({100*covered/len(data):.1f}%)")

    addrs = Counter(f["addr"] for f in frames)
    cmds = Counter(f["cmd"] for f in frames)
    print(f"\n# Addresses seen: " +
          ", ".join(f"{a:04X}(x{c})" for a, c in addrs.most_common()))
    print(f"# Commands seen:  " +
          ", ".join(f"{c:02X}(x{n})" for c, n in cmds.most_common()))

    # group by (addr, cmd, len)
    groups = defaultdict(list)
    for f in frames:
        groups[(f["addr"], f["cmd"], f["len"])].append(f)
    print(f"\n# {len(groups)} distinct (addr, cmd, len) message types:")
    print(f"# {'ADDR':>5} {'CMD':>3} {'LEN':>3} {'N':>4}  dir   payload field stability")
    for (addr, cmd, ln), fs in sorted(groups.items(),
                                      key=lambda kv: -len(kv[1])):
        direction = "RESP" if cmd & 0x80 else "REQ "
        # per-position: constant value or '..' if it varies
        stab = []
        for p in range(ln):
            vals = {f["payload"][p] for f in fs}
            stab.append(f"{next(iter(vals)):02X}" if len(vals) == 1 else "..")
        print(f"  {addr:04X} {cmd:>3X} {ln:>3} {len(fs):>4}  {direction}  "
              f"{' '.join(stab) if stab else '(empty)'}")

    # request/response pairing summary
    print("\n# Request/response command pairs (addr: req->resp):")
    by_addr_cmd = defaultdict(set)
    for f in frames:
        by_addr_cmd[f["addr"]].add(f["cmd"])
    for addr, cs in sorted(by_addr_cmd.items()):
        reqs = sorted(c for c in cs if not c & 0x80)
        resps = sorted(c for c in cs if c & 0x80)
        pairs = []
        for r in reqs:
            mate = r | 0x80
            pairs.append(f"{r:02X}->{mate:02X}{'' if mate in resps else '(?)'}")
        extra = [f"{r:02X}" for r in resps if (r & 0x7F) not in reqs]
        print(f"  {addr:04X}: {', '.join(pairs)}"
              + (f"   unmatched-resp: {', '.join(extra)}" if extra else ""))

    # a few example frames per type (first occurrence)
    print("\n# Example frame per type (first occurrence, full raw):")
    seen = set()
    for f in frames:
        key = (f["addr"], f["cmd"], f["len"])
        if key in seen:
            continue
        seen.add(key)
        dec = decode_payload(f["payload"])
        print(f"  {f['raw'].hex(' ')}")
        if f["payload"]:
            print(f"        payload-0x33: {dec.hex(' ')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binfile")
    ap.add_argument("--json", action="store_true", help="dump frames as JSONL")
    args = ap.parse_args()
    data = open(args.binfile, "rb").read()
    if args.json:
        for f in parse_stream(data):
            print(json.dumps({**f, "payload": f["payload"].hex(),
                              "raw": f["raw"].hex()}))
    else:
        report(data)


if __name__ == "__main__":
    main()
