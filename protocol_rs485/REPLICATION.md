# Replicating NIU N1S packets — groundwork (for later)

The user's intent: be able to **replicate / replay each packet** in a later,
deliberate phase. The frame format and checksum are fully solved, so a
byte-exact frame can already be reconstructed from `(address, command, payload)`.
This file records the plan so the next session can pick it up.

## What already works (today)

`tools/parse.py:build_frame()` is the verified inverse of the parser. It emits a
byte-exact, checksum-correct frame. Confirmed against real bus traffic:

```bash
.venv/bin/python tools/replay.py build --addr 0x20 --cmd 0x02 --payload 38,3b
# -> fe fe fe fe 68 20 df 68 02 02 38 3b 46 16   (identical to the real poll)
```

`tools/replay.py` can also re-emit every frame from a capture file. **All of
this is dry-run by default — nothing is transmitted** until `--transmit` is
passed.

### Payload `+0x33` offset — the one gotcha when forging frames

`--payload` is interpreted as **on-wire** bytes, so *replaying captured frames is
correct as-is*. But the PAYLOAD is DL/T-645 offset-encoded (`on-wire = actual +
0x33`; verified in NIU firmware — it's an ADD, not XOR). To forge a frame from a
**decoded/intended** value (e.g. a chosen SoC or selector), add `--encode`, which
applies `+0x33` per byte for you:

```bash
# build a frame whose decoded payload is 00 01 (on-wire becomes 33 34)
.venv/bin/python tools/replay.py build --addr 0x10 --cmd 0x84 --payload 01 --encode
```

The header (`68 ADDR ~ADDR 68 CMD LEN`), checksum and `0x16` EOF are **plaintext**,
and the checksum is computed over the on-wire (offset) payload — `build_frame()`
already does this. Recipe for any forged frame: `body = 68 ADDR ~ADDR 68 CMD LEN
(actual+0x33 …)`, `CS = sum(body from first 0x68) & 0xFF`, append `0x16`, optional
`FE FE FE FE` prefix. This reproduces the 548/548-valid captures.

## Open before live transmission

1. **RS485 direction control.** Most CH340+RS485 modules auto-toggle DE/RE from
   the TX data, so a plain `serial.write()` is enough. If this module needs
   manual control, use pyserial's `rs485_mode` (`serial.rs485.RS485Settings`)
   or toggle RTS around the write. Verify with a loopback before trusting it.
2. **Bus arbitration.** There is already a master polling the bus. Injecting
   frames blindly can collide with it. Safer options:
   - **Impersonate a slave:** only transmit a node's *response* immediately
     after seeing that node's *request* (the bus is otherwise idle then).
   - **Impersonate the master:** only if the real master can be powered off,
     otherwise two masters will collide.
   - Start by replaying onto a **bench setup / loopback**, not the live vehicle.
3. **Timing.** Responses follow requests within a tight window. Measure the
   request→response latency from `captures/*.jsonl` and reproduce it.

## How to decode payload semantics (needed to make replication *meaningful*)

Replaying constant frames is trivial; making the scooter *do* something or
reading live telemetry needs the field meanings, which require state changes
while capturing:

| Experiment                                   | Expected to move |
|----------------------------------------------|------------------|
| Power cycle / turn key on↔off                | status/handshake fields, the varying request bytes |
| Squeeze throttle (on stand)                  | a speed/current field in a node response |
| Plug/unplug charger                          | a charging-state flag, current field |
| Let battery rest vs. load                    | a voltage field (look for BCD/ASCII digits decoding to a plausible pack voltage) |
| Toggle lights / indicators                   | a controller/dashboard bitfield |

Capture continuously (`tools/sniff.py capture --baud 9600 --seconds N`) across
each change, diff the per-field byte streams (extend `tools/parse.py`'s
field-stability report), and correlate moving bytes with the action.

## Suggested next-session checklist

- [ ] **Capture node 0x31 (BMS) responding** — top priority. In our capture the
      BMS was polled (`31CE 02 02 60 42` = CMD2 pack-data request) but never
      answered (battery absent/asleep). With the battery present, capture its
      `0x82` reply and run the known decoders (`PROTOCOL.md` §6) to read pack
      voltage / SoC / cells / serial directly. Also poll CMD3–CMD6
      (`6F 5B 9D`, `3C 43 52`, `35 35 3D`, `5C 46 75`).
- [ ] Confirm RS485 DE/RE auto-direction (loopback test).
- [ ] Capture during each experiment above; label captures by action.
- [ ] Extend `parse.py` to emit per-field time series aligned to a timestamp
      (decode with `−0x33` first, via `decode_payload()`).
- [ ] Decode at least one live telemetry field (pack voltage) end-to-end and
      check it against a multimeter to pin the scale.
- [ ] Watch for a **second battery at node 0x32** (range-extender pack) — both
      NIU firmwares contain `cmp #0x32` checks.
- [ ] Build a "responder" that answers a chosen node's poll on a bench rig.
- [ ] Only then consider live transmission, impersonating a single slave.
