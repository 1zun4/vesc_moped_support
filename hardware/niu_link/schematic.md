# Schematic implementation specification

This is a sheet-by-sheet circuit specification, not an electrical netlist. Unknown
connector cavities and MCU pads are deliberately not assigned by guesswork.

## 01 — HV input and auxiliary supplies

External nets: `PACK_P`, `PACK_N`. Internal domains: `HV_PROTECTED`, `AUX_12V`,
`LOGIC_5V`, `LOGIC_3V3`, `MODEM_VBAT`, `NIU_SUPPLY`, `POWER_FAULT`.

1. Fuse the board branch at the pack takeoff, with DC interrupt rating adequate for
   the pack. Add reverse-polarity protection, inrush control and an input filter.
2. Size surge limiting from measured pack/harness transients. A TVS standoff value
   alone is not evidence that its clamp voltage protects a 140 V controller.
3. Feed the NIU converter and auxiliary converter independently. The auxiliary
   rail powers the gateway before ignition so it can answer startup messages.
4. Provide independent output overvoltage sensing and a series disconnect on the
   NIU rail. Disable switching and isolate the output on overvoltage; do not rely
   solely on software or converter EN to handle a shorted power switch.
5. Regulate logic and modem rails separately. Modem rail voltage, burst current,
   bulk capacitance and UART level shifting follow the selected modem hardware
   manual. Do not assume every modem uses 3.3 V UART or a 5 V supply.
6. Add divided/filtered measurements for pack and NIU output voltage, converter
   temperature and fault state. Verify divider resistor voltage ratings, power,
   ADC source impedance and input protection under loss of MCU power.

HV and connector protection must remain outside the antenna keepout and analog
input area. Select creepage/clearance from voltage, pollution, enclosure, coating
and fabrication process before layout; a generic low-voltage board rule is invalid.

## 02 — Vehicle gateway

Candidate STM32G0B1RE supplies two independent FDCAN controllers. Assign:

| Peripheral | Function | Required signals |
| --- | --- | --- |
| FDCAN1 | NIU NQiX | TX, RX, transceiver standby |
| FDCAN2 | VESC network | TX, RX, transceiver standby |
| USART | N1S RS485 | TX, RX, DE; /RE independently accessible |
| ADC | Local measurements | Throttle monitor, pack sense, NIU rail sense, temperature |
| GPIO/interrupt | Vehicle inputs | Brake, sidestand, start, mode left/right, cruise, ignition |
| SWD | Recovery/programming | SWDIO, SWCLK, NRST, reference voltage, ground |

Reserve external clock pads if required to meet the CAN timing budget. Decouple
every supply pin, connect every VSS/VSSA pin explicitly, and follow ST's reset,
boot and VDDA recommendations. Complete a package-specific alternate-function
allocation before drawing wires or choosing the PCB footprint.

Use an independent watchdog and brownout reset. `NIU_CAN_STB`, `VESC_CAN_STB` and
`RS485_DE` need hardware reset-state resistors; firmware boot must not drive a bus.

## 03 — CAN and RS485

Each CAN transceiver has its own 100 nF local bypass, supply bulk capacitance as
required by its datasheet, ESD protection at the connector and provision for an
optional common-mode choke. CAN protection clamp and capacitance must match the
transceiver's limits and intended bitrate. Include accessible CANH/CANL test pads.

Provide switchable 120 ohm termination per physical bus endpoint, default open.
The gateway and ESP share one short VESC bus segment: do not fit separate 120 ohm
terminators for both transceivers on that same endpoint. Measure the installed
network termination with power off. A transceiver rated for CAN FD does not prove
that the NQiX uses CAN FD; start with passive bitrate/frame-format discovery.

RS485: route `NIU_RS485_A/B` through suitable protection; provide optional 120 ohm
termination and optional failsafe bias resistors, default unpopulated until the
existing bus is measured. DE defaults low. Firmware waits for transmission-complete
(including the last stop bit), releases DE, then resumes receive. Verify A/B
polarity against observed traffic rather than assuming vendor naming agrees.

## 04 — NIU connector and input conditioning

`legacy_connector.csv` records **PCB pad numbers**, not verified vehicle cavity
numbers. Use it only as a starting point for continuity mapping. Pin 27 is routed
through a divider to THROTTLE; the raw PCB net itself is unnamed.

For each switch wire, measure open-circuit voltage, active voltage, polarity and
source impedance. Populate a variant-specific divider/comparator or transistor
interface with current limiting and transient protection. ACC_LOCK, BRAKE_LAMP
and EABS names are not evidence of 3.3 V compatibility. Do not connect them directly
to MCU pins. Provide input test points on both sides of protection.

Keep throttle supply/signal/return to the VESC ADC as a dedicated harness path for
the first N1S revision. Add high-impedance protected monitoring only after its
voltage range is verified. Keep brake priority and traction inhibit in the VESC
control path, independent of WiFi. Do not substitute an unvalidated DAC throttle.

NQiX connector positions remain unassigned. Supply return, ignition feed, ECU feed,
CAN pair and any physical throttle/brake wires must be identified independently.
Use a model-keyed adapter harness if matching board-mount plugs cannot be verified.

## 05 — Connectivity

ESP32-C3 running a new VESC Express hardware target, with its own VESC CAN
transceiver. Allocate modem UART, modem control/reset/wake, USB/programming and
CAN before optional storage. Retaining VL Link's CAN GPIO0/1 is a candidate only;
boot strapping and remaining module pins require a complete allocation review.

Select a modem against the VESC Express/IoT driver AT command support, local LTE
bands and SIM service. A nano-SIM socket alone does not deliver cellular access.
Include SIM ESD close to the socket, RF connector/matching provision, modem power
switch, and a separately controllable reset. Check RF ground/keepout against the
module integration guide. No exact modem is released in this design draft.

VESC Tool uses local WiFi or the cellular TCP hub path. Verify both explicitly on
phone and laptop; BLE is an additional path. Do not treat LTE registration or an
MQTT upload as evidence that VESC Tool tunnelling works.

## 06 — Service and grounding

USB supplies only the service domain through reverse-current blocking. It must
not energize the NIU harness or backfeed the vehicle rail. Clearly label whether
USB ground is tied to pack negative; prefer isolated service equipment for powered
vehicle bring-up. An isolated DC/DC alone does not make a board isolated if CAN,
RS485 or USB reconnect the grounds. Add test points for every rail and bus.

Four layers are a starting layout choice, not a fixed size commitment. Keep the
power switching loops compact, RF at an enclosure edge, and noisy power return
currents away from throttle sensing. Choose board outline only after connector,
magnetics, thermal dissipation and enclosure constraints are known.
