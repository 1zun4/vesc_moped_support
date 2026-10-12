# Verification and release gates

## Measurements that cannot be inferred from the repository

| ID | Required evidence | Design it unlocks |
| --- | --- | --- |
| M1 | External step-down model, measured output and load wiring | NIU setpoint and topology |
| M2 | Continuous, startup and accessory load on that rail | Magnetics, current limit, thermal budget |
| M3 | N1S/NQiX connector photos, cavity numbering and continuity map | Footprints or keyed adapter harness |
| M4 | Signal voltage/polarity in all switch states | Input conditioning and throttle path |
| M5 | NQiX passive CAN captures, ignition and battery states labelled | Protocol and wake-up implementation |
| M6 | Pack voltage range and measured transients | HV parts and input protection |
| M7 | Enclosure dimensions, ambient temperature and mounting | Layout, thermal and RF design |

## Bench sequence

1. Validate connector orientation with an unpowered continuity fixture. Keep
   unverified cavities disconnected; verify the absence of raw pack voltage on
   logic/OEM supply pins.
2. Bring up low-voltage rails from a current-limited bench supply, without NIU,
   VESC or the battery. Check power sequencing, reset defaults, watchdog, USB
   backfeed and modem burst immunity.
3. Bring up the HV converter separately with a dummy load and a suitably rated,
   current-limited source. Sweep verified battery range, startup load, load steps,
   shutdown and temperature. Test output overvoltage disconnect by controlled
   fault injection before connecting OEM electronics.
4. Check both CAN channels independently with known peers, bus termination,
   bus-off recovery and listen-only operation. Confirm NIU traffic never leaks
   unfiltered onto VESC CAN. Confirm RS485 DE release at the final stop bit.
5. Replay N1S captures into a bench gateway; compare replies and timing against
   existing captured vectors. Test checksum errors, truncated frames, missing
   polls and ignition restart. Establish speed calibration before live display use.
6. With traction disabled, verify OEM wake-up and startup. Test brake, sidestand,
   start and cruise transitions, held buttons during reset and stale controls.
   Re-enable traction only after independent stop/inhibit behaviour is demonstrated.
7. Test VESC Tool on phone/laptop via WiFi and SIM TCP hub, including outages and
   reconnects. Network faults must not reset the gateway or re-enable traction.

## Fabrication release checklist

- [ ] M1–M7 recorded, with remaining optional features explicitly excluded.
- [ ] Full component schematic, exact manufacturer parts and footprints reviewed.
- [ ] MCU alternate-function allocation and modem voltage/pin requirements verified.
- [ ] Converter calculations, compensation and thermal/transient results reviewed.
- [ ] Schematic/PCB synchronised; ERC/DRC reviewed with documented intentional exceptions.
- [ ] Ground connectivity, current paths and HV clearance reviewed independently.
- [ ] Prototype results demonstrate protection, reset and traction inhibit behaviour.

None of these hardware gates is implied by passing the Python checks.
