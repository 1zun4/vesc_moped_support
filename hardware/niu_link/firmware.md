# Gateway and connectivity firmware contract

## Preserve the existing VESC control split

The current `code_esp.lbm` samples a TCA9535 and sends standard CAN ID 200
(decimal, 0xC8), DLC 8. `code_stm.lbm` consumes it with a 0.30 s timeout.

| Byte | Meaning | Encoding |
| --- | --- | --- |
| 0 | Start button | 0/1 |
| 1 | Mode left | 0/1 |
| 2 | Mode right | 0/1 |
| 3 | Sidestand down | 0/1 |
| 4 | Cruise button | 0/1 |
| 5 | Brake active | 0/1 |
| 6–7 | Reserved | 0 |

Proposed gateway publication period: 50 ms. This is a new target, not the exact
legacy sampling period. Only one node publishes this ID: disable the old ESP
publisher when the new gateway is enabled. On the ESP, remove the TCA9535 pin
reuse and u-blox shutdown; connectivity firmware must keep its modem/GNSS pins.

Keep the motor-side timeout active. Before deployment harden the receiver to
validate DLC, boolean values and reset state, and require a release-then-press
start sequence after a reset or timeout. A held start button on recovery must not
re-enable traction. Brake and sidestand must override cruise. Delayed packets,
bus-off, stuck switches and MCU resets are fault-injection cases.

The existing `event-data-rx` handlers evaluate received Lisp. That may be normal
for the package UI but must be reviewed before exposing a remote command path.
Do not assume CAN ID filtering authenticates internet users. Provision credentials,
avoid a publicly exposed unauthenticated listener, and require a stationary service
state for configuration/firmware updates. Do not add remote throttle controls.

## N1S personality

Start with 9600 baud, 8N1, half-duplex. Preserve the OEM ECU as bus master and
emulate only the removed motor controller at address 0x20. Existing handshake
vectors and telemetry construction live in `protocol_rs485/tools/emulate.py`.
Use the current PROTOCOL.md as the source; REPLICATION.md contains older planning
notes and must not be mistaken for the current implementation status.

Parse incoming frames incrementally, bound payload length, validate checksum and
destination, and reply only to supported requests. Use captured startup order and
timing. Do not periodically broadcast fabricated dashboard frames or run a second
master. Measure latency from the end of the request, not its first byte.

Translate VESC speed only after raw-to-dashboard scaling, direction and saturation
are verified. Unknown status bytes stay explicitly experimental. Battery SoC must
come from the actual 30S battery/BMS or a documented estimate, not the regulated
NIU rail voltage. Do not emulate node 0x31 if an OEM BMS already answers it.

## NQiX personality

Start listen-only on the NIU CAN channel with transmit disabled in hardware reset
state. Determine bitrate, classical/FD format, termination, wake-up, controller
heartbeat, counters/checksums and BMS dependencies from labelled captures. Keep
unknown frames local; never blanket-forward them to VESC CAN. Hardware support
for CAN does not constitute NQiX protocol support.

## Connectivity

Use VESC Express with a new board target and a verified modem driver/library.
ESP is a VESC CAN node alongside the gateway. Confirm local WiFi discovery/direct
connection and end-to-end TCP hub access over SIM from both phone and laptop.
Exercise loss of WiFi, SIM removal, LTE reconnect, modem reset and firmware update
without disturbing the gateway. Confirm the selected modem supports the actual
socket transport; MQTT telemetry alone is not a VESC Tool connection.
