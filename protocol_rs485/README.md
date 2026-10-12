# NIU N1S — RS485 protocol reverse engineering

Sniffing and documenting the internal RS485 bus of a **NIU N1S** electric
scooter, reached through a CH340 USB↔RS485 adapter on `/dev/ttyUSB0`.

**Status:** frame format & checksum fully solved (548/548 captured frames valid,
9600 8N1). Payload semantics mostly open (vehicle was parked during capture).
See **[PROTOCOL.md](PROTOCOL.md)** for the full spec and **[REPLICATION.md](REPLICATION.md)**
for the packet-replay groundwork.

## Frame in one line
```
[FE FE FE FE]?  68  ADDR  ~ADDR  68  CMD  LEN  PAYLOAD[LEN]  CS  16
                            checksum = sum(from first 68 .. last payload) & 0xFF
```
Nodes: `0x10 0x20 0x31 0x70`. `CMD` bit7 = direction (req/resp). `~ADDR = ADDR^0xFF`.

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install pyserial          # already done in this checkout
```
The user must be in the `uucp` group (Arch) to access `/dev/ttyUSB0`.

## Quickstart
```bash
# 1. discover baud (already known: 9600)
.venv/bin/python tools/sniff.py sweep

# 2. capture traffic
.venv/bin/python tools/sniff.py capture --baud 9600 --seconds 30 --out captures/run1

# 3. parse + validate + catalogue
.venv/bin/python tools/parse.py captures/run1.bin

# 4. build/replay frames (dry-run; --transmit to actually send — LATER)
.venv/bin/python tools/replay.py build --addr 0x20 --cmd 0x02 --payload 38,3b
```

## Layout
```
tools/sniff.py     baud sweep + timestamped capture (passive)
tools/parse.py     structural parser, checksum validator, build_frame()
tools/replay.py    frame builder / replayer (dry-run by default)
captures/          raw .bin + timestamped .jsonl captures
PROTOCOL.md        full protocol spec
REPLICATION.md     plan for replicating packets later
```

**Safety:** everything here is passive (listen-only) except `replay.py --transmit`,
which is intentionally gated for a later, deliberate phase. Injecting onto a live
bus can collide with the scooter's real master — see REPLICATION.md.
