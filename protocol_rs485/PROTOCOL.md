# NIU N1S — Internal RS485 Bus Protocol (reverse-engineered)

Status: **frame format, checksum, addressing, `+0x33` payload encoding, the
controller start-up handshake, and the speed field map are solved.** Battery and
some payload fields are still being worked out. We have moved from passive
sniffing into **active emulation** (answering polls / injecting frames); see §10
for the current transmit status.

---

## 1. Physical layer

| Property      | Value                                                       |
|---------------|-------------------------------------------------------------|
| Bus           | RS485 (half-duplex, differential), multi-drop               |
| Adapter       | QinHeng CH340 USB-serial (`1a86:7523`) → RS485 transceiver   |
| Device node   | `/dev/ttyUSB0` (driver `ch341`, owner `root:uucp`)          |
| **Baud rate** | **9600**                                                    |
| Framing       | **8N1** (8 data bits, no parity, 1 stop bit)                |
| Flow control  | none                                                         |

Baud found by sweeping 2400–230400 (`tools/sniff.py sweep`); ≥19200 collapses into
oversampled garbage. 9600 8N1 yields 100% checksum-valid frames.

---

## 2. Frame format

```
 ┌──────────────┬─────┬──────┬───────┬─────┬─────┬─────┬──────────────┬─────┬─────┐
 │ FE FE FE FE  │ 68  │ ADDR │ ~ADDR │ 68  │ CMD │ LEN │ PAYLOAD[LEN] │ CS  │ 16  │
 │ (preamble)   │ SOF │      │       │ SOF │     │     │              │     │ EOF │
 └──────────────┴─────┴──────┴───────┴─────┴─────┴─────┴──────────────┴─────┴─────┘
        ^optional        \────────── covered by checksum ──────────/
```

| Field    | Size  | Meaning |
|----------|-------|---------|
| Preamble | 0 or 4 | `FE FE FE FE` wake/sync; present on polls, usually absent on replies. **Not** in checksum. |
| SOF      | 1     | Start delimiter, always `0x68`. |
| ADDR     | 1     | Node address: `0x10`, `0x20`, `0x31`, `0x70`. |
| ~ADDR    | 1     | `ADDR ^ 0xFF` (redundancy). |
| SOF₂     | 1     | Second `0x68` (header/data separator). |
| CMD      | 1     | Function code. **Bit 7 = direction**: 0 = request (master→node), 1 = reply (node→master). |
| LEN      | 1     | Payload length (decimal). |
| PAYLOAD  | LEN   | Command-specific data, `+0x33` encoded (§4). |
| CS       | 1     | `(sum of bytes from first 0x68 .. last payload) & 0xFF`. |
| EOF      | 1     | End delimiter, always `0x16`. |

`ADDR/~ADDR`: `10 EF`, `20 DF`, `31 CE`, `70 8F` (second byte = complement).
Worked checksum — `68 20 DF 68 02 02 38 3B`: sum = `0x246` → `& 0xFF = 0x46` ✓.

This `68…68…CS 16` + `FE` wake-up + sum-from-SOF checksum + `+0x33` data offset is
**DL/T 645** (Chinese smart-meter family, IEC 60870-5-1 FT1.2 lineage), with NIU's
own compact `ADDR/~ADDR` addressing and command set.

---

## 3. Payload `+0x33` offset encoding

Every PAYLOAD byte is transmitted as `actual + 0x33`. **Decode = subtract 0x33**
per byte; multi-byte big-endian values decode as `u16_be − 0x3333`. So a run of
`0x33` decodes to `0x00`. Header, CS and EOF are plaintext; the checksum is over
the *encoded* bytes. (`tools/parse.py:decode_payload()` does the subtraction.)

---

## 4. Bus topology & roles

A single **master** (the central ECU / main control unit — *unaddressed*, still
runs when the motor controller is unplugged) drives the bus: it **pushes** the
display frame to the dashboard and **polls** the other nodes once per ~300 ms.

| Node  | Role | Notes |
|-------|------|-------|
| (master) | **Central ECU / main control unit** | Sends all polls + the `10EF 04` display push. Not addressable. |
| `0x10` | **Dashboard / display** | Pure slave; renders the `10EF 04` frame it's sent (firmware-confirmed). |
| `0x20` | **Motor controller** | The unit the user unplugs. Does a boot handshake (§5), then reports speed telemetry (§6). |
| `0x31` | **BMS / battery pack** | Absent/silent in our rig (polled, never replies). Format known from `niu-bms-readout` (§8). |
| `0x70` | **Telematics / alarm module** | Replies on the live bus; identity not fully confirmed. |

Master tolerates ~30 ms reply latency (real slaves answer 12–33 ms after a poll;
bus is idle in between). One poll cycle ≈ 300 ms; the display push recurs at 3.3 Hz.

---

## 5. Motor-controller (0x20) start-up handshake  ← key to emulation

At ignition-on the ECU will **not** trust the controller (and keeps the dashboard
blank) until this exchange completes. Captured byte-for-byte (`captures/calib`):

| # | ECU poll (request)                 | Controller reply |
|---|------------------------------------|------------------|
| 1 | `68 20 df 68 01 01 36 07 16` (init, repeated ~5×/s until answered) | `68 20 df 68 81 10 80 81 64 67 6a 76 64 75 67 66 64 68 63 67 65 6a 17 16` (16-byte identity) |
| 2 | `68 20 df 68 05 02 7a 70 c0 16`     | `68 20 df 68 85 01 01 56 16` |
| 3 | `68 20 df 68 01 01 37 08 16`        | `68 20 df 68 81 01 49 9a 16` |
| 4 | `68 20 df 68 06 01 44 1a 16`        | `68 20 df 68 86 00 55 16` |
| → | then steady `68 20 df 68 02 02 38 3b 46 16` (cmd02) | telemetry (§6) |

`cmd01` payload `36`/`37` was constant across boots (not a random nonce), so the
replies can be replayed verbatim. To impersonate the controller you must be
answering **before** ignition-on so the ECU gets the identity.

---

## 6. Motor-controller (0x20) telemetry — `cmd02 → cmd82`

Reply: `68 20 df 68 82 0c <12 payload> CS 16`. Template (idle/parked) decodes
(`−0x33`) to: `3c 34 5a 01 00 2b 00 00 00 00 88 80`.

| Decoded pos | Field | Notes |
|-------------|-------|-------|
| 8–9 | **Speed** | signed 16-bit (pos8 = high). Hand-spin gave `00 05`…`FF FB` (≈ ±5). Forwarded to the dashboard (§7). |
| 10  | **Status/mode bitfield** | changed with mode buttons / READY / sidestand / alarm (seen `0x88 0xA8 0x80 0xA0`). |
| 0–7, 11 | constant (`3c 34 5a 01 00 2b … 80`) | likely controller id/config; meaning TBD. |

---

## 7. Display frame (0x10) — `cmd04`, master → dashboard

The ECU pushes `68 10 ef 68 04 0f <15 payload> CS 16` at 3.3 Hz; the dashboard
renders it (and ACKs `68 10 ef 68 84 01 34 88 16`). Template decodes to
`80 50 01 00 aa 23 00 00 00 00 00 00 0e XX bf`.

| Decoded pos | Field | Notes |
|-------------|-------|-------|
| **3** | **Speed (km/h shown)** | tracked the controller speed during the motor-spin (0→1→2→0). One byte. |
| 0, 1 | heartbeat / toggling counters | change every frame; not data. |
| 13 | slow counter | increments minutes-scale (odometer/uptime?). |
| 4–5 (`aa 23`), 14 (`bf`) | constant | TBD. |
| 6–12 | zero when idle | candidate fields for current/power/trip/etc. |

Battery % field on the display is **not yet located** (the BMS was absent, so the
gauge read 0 throughout). Finding it is the current focus (§10).

---

## 8. BMS (node 0x31) command & decode reference

From `phlundblom/niu-bms-readout` (real decoder). Requests (trailing byte = CS):

| Function       | Request     | Reply length | Decoded fields (`−0x33` / `−0x3333`, big-endian) |
|----------------|-------------|--------------|--------------------------------------------------|
| CMD2 pack data | `60 42 75`  | 15-byte payload | **voltage** `(u16@0-1−0x3333)/10` V; **current** `(u16@2-3−0x3333)/10` A; **SoC** `byte@6−0x33` %; time-left `byte@8`; **temps** `byte@9..12−0x33` °C |
| CMD3 cells     | `6F 5B 9D`  | 40-byte | 20× cell `(u16−0x3333)/1000` V |
| CMD4 serial    | `3C 43 52`  | 16-byte | `chr(byte−0x33)` |
| CMD5 versions  | `35 35 3D`  | 2-byte | SW/HW nibbles |
| CMD6 cycles    | `5C 46 75`  | u16 | cycle count `u16−0x3333` |

Reply frame: `68 31 ce 68 82 <LEN> <payload> CS 16`. To report SoC = 67%, set
decoded payload byte 6 to 67 (on-wire `0x76`). Built by `tools/simulate.py:battery_frame()`.

---

## 9. Tooling

| Tool | Purpose |
|------|---------|
| `tools/sniff.py` | baud sweep + timestamped passive capture |
| `tools/parse.py` | structural parser, checksum validator, `build_frame()`, `decode_payload()` |
| `tools/timeline.py` | per-byte change timeline of a capture (used to map speed/handshake) |
| `tools/simulate.py` | slave responder: BMS (`0x31`) + controller (`0x20`) cmd02 |
| `tools/emulate.py` | **full** controller emulator incl. start-up handshake + injected speed + BMS; watches the display frame; manual RTS direction |
| `tools/override_display.py` | injects the `10EF 04` display frame directly (timing-forgiving TX test) |
| `tools/correlate.py` | A/B test whether injected slave data reaches the display |

Captures in `captures/` (`calib.*` = the controller-connected calibration run).

---

## 10. Live emulation / transmit status  ← current blocker

**Receive works perfectly** — every frame decodes, 100% checksum-valid.

**Transmit is unconfirmed.** The CH340's TX LED flashes (bytes leave the adapter),
but **no bus device has been observed to accept anything we send**:
- BMS impersonation (SoC 67) → battery stayed 0.
- Full controller handshake replay → ECU kept re-sending `cmd01`; never booted.
- Direct `10EF 04` display override (timing-forgiving) → speedometer never moved.
- Tried auto-direction and manual RTS-high / RTS-low; `ch341` has **no kernel
  `rs485_mode`** (`TIOCSRS485` → ENOTTY), so only manual `ser.rts` toggling is possible.

Leading hypotheses: (a) the RS485 transceiver isn't actually driving the
differential pair / direction (DE/RE) isn't switched correctly for our writes, or
(b) Python-over-USB reply latency is outside the ECU's accept window (a real
controller is a microcontroller replying in <1 ms). A microcontroller
(Arduino/ESP32 + RS485) emulator is the robust fallback if the PC path can't be made to work.

**Current test plan:** keep the **real controller connected** (so the ECU boots
normally) and inject **only the BMS** (`0x31`, which is absent → no collision) to
see if battery 67% appears — isolating the transmit-acceptance question in a
fully-booted system.

---

## 11. References
- `phlundblom/niu-bms-readout` — https://github.com/phlundblom/niu-bms-readout
- `axelmuhr/niu_n1s_ecu` — https://github.com/axelmuhr/niu_n1s_ecu
- `axelmuhr/NIU_gen2_dashboard_fw` — https://github.com/axelmuhr/NIU_gen2_dashboard_fw
- Elektroroller-Forum t=8776 — https://www.elektroroller-forum.de/viewtopic.php?t=8776
- MyNIU.org — https://www.myniu.org/reverse-engineering-the-ecu/ , https://www.myniu.org/2nd-gen-dashboard/
- DL/T 645 / `+0x33` / FE wake-up — https://www.gurux.fi/DLT645
