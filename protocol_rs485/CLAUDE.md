# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Reverse-engineering of the **internal RS485 bus of a NIU N1S electric scooter**,
reached through a CH340 USB↔RS485 adapter. The bus runs a master that cyclically
polls four slave nodes; we sniff it passively. The frame format and checksum are
fully solved; payload field *semantics* are mostly open (the scooter was parked
during capture, so live values never moved). Full spec: `PROTOCOL.md`. Replay
groundwork: `REPLICATION.md`.

## Hardware / environment (must hold to read the bus)

- Adapter: QinHeng CH340 (`1a86:7523`) → `/dev/ttyUSB0` (driver `ch341`, owner `root:uucp`).
- Access: the user must be in the **`uucp`** group (Arch convention) — no sudo needed.
- Line settings: **9600 8N1**, no flow control.
- pyserial lives in a repo-local **`.venv`** (system Python is externally-managed,
  so always invoke tools as `.venv/bin/python …`, not bare `python`).

## Commands

```bash
# discover baud (already known to be 9600) — scores each rate for frame-likeness
.venv/bin/python tools/sniff.py sweep [--seconds 2.5]

# passive timestamped capture -> captures/<name>.bin + .jsonl
.venv/bin/python tools/sniff.py capture --baud 9600 --seconds 30 --out captures/<name>

# structural parse + validate every checksum + print the message catalogue
.venv/bin/python tools/parse.py captures/<name>.bin
.venv/bin/python tools/parse.py captures/<name>.bin --json   # one JSON frame per line

# build / replay frames — DRY-RUN by default; prints bytes, transmits nothing
.venv/bin/python tools/replay.py build --addr 0x20 --cmd 0x02 --payload 38,3b
.venv/bin/python tools/replay.py replay --bin captures/<name>.bin --limit 20
```

There is no build/lint/test suite; verification is empirical — re-capture from the
bus and confirm `parse.py` reports **100% checksum-valid** frames.

## Architecture

Three small, single-purpose tools form a pipeline `sniff → parse → replay`:

- **`tools/sniff.py`** — the only code that opens the serial port for *reading*.
  `sweep` brute-forces baud rates and scores each by entropy/periodicity (used to
  find 9600). `capture` records raw bytes with arrival timestamps. Knows nothing
  about NIU framing — it is a generic UART recon tool.
- **`tools/parse.py`** — the protocol model. `parse_stream()` resync-walks a raw
  byte stream and emits validated frames; `build_frame()` is its verified inverse
  (reproduces real bus frames byte-for-byte). `report()` prints the address/command
  catalogue and per-payload-position field stability. **This is the single source
  of truth for the frame grammar** — `replay.py` imports `build_frame`/`parse_stream`
  from here; keep the two in sync by construction (never duplicate the grammar).
- **`tools/replay.py`** — frame builder/replayer for the (later) replication phase.
  Transmitting is gated behind `--transmit`; everything else is dry-run.

`captures/` holds `.bin` (raw bytes) + `.jsonl` (timestamped chunks) pairs.
`captures/long_9600.bin` is the reference 30s capture (548 valid frames).

## Frame grammar (the one thing to internalize)

```
[FE FE FE FE]?  68  ADDR  ~ADDR  68  CMD  LEN  PAYLOAD[LEN]  CS  16
```
- `FE` preamble is optional and **excluded** from the checksum.
- `~ADDR = ADDR ^ 0xFF` (redundancy). Real node addresses: `0x10 0x20 0x31 0x70`.
- `CMD` bit 7 = direction (0 = request master→node, 1 = response). Pairs: 02↔82, 04↔84.
- `CS = (sum of bytes from the first 0x68 through the last payload byte) & 0xFF`.
- **Family: NIU-customised DL/T 645** (Chinese smart-meter protocol, FT1.2 lineage).
- **PAYLOAD is `+0x33` offset-encoded** (`actual = on-wire − 0x33`; 16-bit numbers
  are big-endian → `u16_be − 0x3333`). Header/CS/EOF are plaintext. Use
  `parse.py:decode_payload()` to interpret, and `replay.py --encode` to forge.

Node map (see `PROTOCOL.md` §5–6): `0x31`=**BMS** (decoders known), `0x10`=**dashboard**,
`0x20`=**motor controller**, `0x70`=**ECU/telematics**. A second battery may appear at `0x32`.

## Safety / conventions

- All capture is **passive**. The only code path that writes to the bus is
  `replay.py --transmit`; it is intentionally gated because a real master is
  already polling and blind injection collides. Treat live transmission as a
  deliberate, separate step (see `REPLICATION.md`).
- Decoding payload semantics requires capturing while changing vehicle state
  (throttle, charger, power) — see the experiment table in `REPLICATION.md`.
