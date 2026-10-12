# NIU Link PCB implementation plan — TSCircuit

Status: implementation plan, 2026-10-12. No implementation phase below is complete
merely because a specification exists. TSCircuit/TSX is the design source of truth.

## 1. Product and scope

Build one integrated PCB that connects original NIU electronics to a VESC motor
controller and provides local WiFi and cellular/SIM access from phone and laptop
through VESC Tool. Support two vehicle variants:

- **N1S:** original controller connector, RS485 and verified physical controls.
- **NQiX:** original controller connector and a separate NIU CAN interface. Hardware
  provision and verified protocol support are separate milestones.

The VESC receives raw battery power directly. The gateway's integrated converters
power the original NIU electronics and its own logic/connectivity. Motor current
does not flow through this PCB. Assume 30S at 4.2 V/cell (126 V fully charged) for
planning; confirm chemistry, minimum operating voltage and transients before release.

Retain the OEM ECU's functions wherever practical. Support the original vehicle
plug through a verified mating connector or documented model-specific adapter
harness. Do not assume N1S and NQiX share connector assignments.

Revision A includes WiFi, SIM connectivity, RS485, independent NIU/VESC CAN domains,
vehicle input conditioning, programming/recovery and integrated power conversion.
GNSS, large logging storage and continuously available parked connectivity are
optional until their power and pin budgets are resolved. No remote throttle feature.

## 2. Implementation architecture

| Block | Initial implementation decision |
| --- | --- |
| Vehicle gateway | MCU with two independent CAN controllers; STM32G0B1RE is the current candidate |
| NIU side | One protected CAN transceiver and one protected half-duplex RS485 transceiver |
| VESC side | Gateway CAN transceiver; separate ESP CAN transceiver on the same VESC bus |
| Connectivity | ESP32 module with VESC Express, compatible cellular modem, SIM socket and antennas |
| OEM supply | Integrated HV converter with verified output setpoint, current capability and independent overvoltage disconnect |
| Auxiliary supplies | Independent startup supply for gateway/connectivity, then logic and modem regulators |
| Controls | Conditioned physical inputs; preserve a defined VESC throttle/brake path |

The gateway processes vehicle inputs independently of modem/network tasks. NIU CAN
and VESC CAN remain separate physical buses. Translation is explicit; unknown NIU
frames are not forwarded. Shared signal grounds do not provide galvanic isolation.

Existing part suggestions are candidates, not a frozen BOM. Final MCU, ESP module,
modem, regulator and connector selection follows datasheet and pin-budget review.

## 3. Repository and reproducible workflow

Implement under `hardware/niu_link/tscircuit/`, preserving `bridge_n1s/` as reference.
Do not modify the legacy PCB to make it resemble generated output.

| Path | Intended contents |
| --- | --- |
| `package.json`, lockfile | Pinned toolchain and build/check/render/export commands |
| `src/NiuLink.tsx` | Top-level board composition and physical outline |
| `src/blocks/` | PowerInput, NiuSupply, AuxSupply, Gateway, CanInterfaces, Rs485, VehicleInputs, Connectivity, Service |
| `src/parts/` | Verified symbols, footprints and manufacturer part bindings |
| `src/variants/` | N1S/NQiX population and harness definitions |
| `design/requirements.json` | Requirements, evidence, assumptions and unresolved values |
| `design/pinmap.csv` | MCU/module pad assignments, functions, voltage domains and reset states |
| `design/bom.csv` | Exact parts, alternates, ratings and sourcing evidence |
| `tests/` | Circuit connectivity, variant and export regression checks |
| `scripts/` | Repeatable build, validation and artifact generation |
| `build/` | Generated output; ignored locally and uploaded as CI artifacts |

Read and use the official [TSCircuit agent skill](https://github.com/tscircuit/skill)
and [documentation](https://docs.tscircuit.com/) during implementation. Pin the
selected version and record the skill revision. Establish commands from that
version's CLI help; do not invent export flags or assume every advertised feature
is available in the installed release.

TSX and checked-in supporting assets remain authoritative. KiCad exports are for
review/interoperability. Any essential export correction must become a repeatable
script or a source change, not a one-off GUI edit that the next build erases.

## 4. Phase A — Verify the toolchain before building the full board

1. Create a small fixture with a custom connector, one IC, decoupling, a ground
   pour, a keepout, mounting hole and deliberately separated voltage domains.
2. Demonstrate TSX build, schematic rendering, PCB rendering, 3D review and the
   required manufacturing exports using the pinned TSCircuit version.
3. Inspect pad numbering, net connectivity, plated/non-plated holes, outline,
   copper pours, clearances and exported footprint orientation.
4. Inject a disconnected pin and a clearance violation. Verify which checks detect
   them; record gaps. Where TSCircuit lacks an essential check, add an independent
   check, for example on a KiCad export, and verify export fidelity first.
5. Confirm controlled placement/routing is possible for power and RF areas. Do not
   substitute unrestricted autorouting for unsupported constraints.

**Exit:** a reproducible fixture with inspected exports, a capability/gap report
and CI commands that fail on known invalid examples. Unsupported requirements
must have an explicit resolution before relying on this toolchain for fabrication.

## 5. Phase B — Establish electrical and mechanical requirements

Create an evidence table with `verified`, `user-reported`, `assumed` or `unknown`
status for every critical value. Unknown electrical values stay null rather than
becoming plausible-looking defaults in a fabrication build.

| Required input | Obtain from | Blocks it affects |
| --- | --- | --- |
| Existing step-down voltage, wiring and actual load | User's N1S setup and measurements | NIU converter |
| Peak/startup and accessory current | Measurements with relevant loads enabled | Magnetics, switches, protection, cooling |
| Connector part/cavity map and orientation | Photos, drawings, continuity tests | Harness and board edge |
| Physical input voltages and polarities | Key-on/off and switch-state measurements | Input conditioning |
| NQiX CAN format, rate and startup exchange | Passive labelled captures | Protocol implementation |
| Battery range, regen/hot-plug envelope | Battery/VESC specifications and measurements | HV protection and ratings |
| Enclosure, mounting, temperature and antenna position | Mechanical constraints | Outline, thermal/RF layout |

Continue toolchain, low-voltage circuitry and component research while measurements
are outstanding. Unverified connector positions may appear in explicitly marked
interface diagrams, but must not be assigned guessed nets on release footprints.

**Exit:** requirements and power budgets sufficient to select exact parts, with
remaining unknowns linked to the specific affected milestone.

## 6. Phase C — Select parts and prove the pin allocation

Select the modem early: supported VESC Express transport/driver, LTE bands,
SIM service, supply bursts, UART levels, antenna and control pins determine much
of the connectivity design. Confirm end-to-end VESC Tool transport with development
hardware where possible before committing a custom modem footprint.

Produce an exact part shortlist with datasheet links/revisions, package drawings,
temperature range, voltage/current limits and alternatives. Allocate all MCU/ESP
pins, including CAN, RS485, modem, boot straps, reset, debug, ADC and wake signals.
Move optional storage/GNSS out if they cannot fit without compromising core functions.

Review every imported symbol/footprint against the manufacturer drawing: pad
numbers, exposed pad, pin 1, dimensions, courtyard and assembly rotation. Preserve
the verified legacy connector map as evidence, not as a manufacturer pinout.

**Exit:** no peripheral pin conflicts, exact BOM candidates, complete rail budget
and reviewed symbols/footprints for every critical component.

## 7. Phase D — Implement the electrical design in TSX

Implement and inspect one block at a time in this order:

1. **Service and low-voltage supplies:** programming, reset, boot states, USB
   backfeed protection, logic power and modem supply isolation.
2. **Gateway:** all supply/ground pins, clock, decoupling, watchdog and measurements.
3. **Buses:** separate NIU/VESC CAN, configurable endpoint termination, RS485
   direction control, bias/termination options and connector protection.
4. **Vehicle interfaces:** measured input conditioning, ignition/wake, throttle
   path and brake/sidestand behaviour. No unprotected battery-domain MCU inputs.
5. **Connectivity:** ESP, modem, SIM, RF matching/antenna provision, controlled
   modem reset and power. Remove the legacy GPIO20/21 expander/modem conflict.
6. **HV conversion:** input fuse/protection/filter/inrush, NIU converter, auxiliary
   converter, sensing and independent NIU overvoltage disconnect.

Select the HV topology from the verified load and output, not from a generic
"150 V" label. In particular LTC3895's output range does not cover 72–84 V.
For the selected circuit calculate worst-case stress, losses, magnetics, startup,
feedback/compensation, reverse current and fault behaviour. Use manufacturer models
or a separate suitable SPICE tool when the TSCircuit simulation path cannot model
the chosen controller accurately. Simulation results need stated assumptions.

**Exit:** complete reviewable schematic generated from TSX, exact part bindings,
no unexplained connectivity errors, power calculations and reviewed fault paths.
The existing sizing examples are not evidence that this phase has been completed.

## 8. Phase E — Physical design and routing

Start with a four-layer proposal; select the final stackup and size after the
power, connector and enclosure requirements are known. Partition HV input/power,
NIU connectors, gateway/analog and RF/connectivity regions. Establish grounding
and return paths before placing traces.

Fix connector and mounting positions first. Then place converter switching loops,
decoupling, sensitive feedback/sense networks and RF components following reference
layouts. Encode clearances, keepouts and routing intent in source where supported.
Use controlled routes for switching power, current sensing, RF and sensitive analog.
Autoroute the remaining signals within verified constraints.

Review copper in every layer, not only the 3D view: loop area, current/thermal
capacity, reference-plane continuity, stubs, via placement, antenna keepouts and
creepage/clearance. Resolve net errors by fixing the circuit or layout; never by
removing a connection from the design to make the build pass.

**Exit:** fully routed board with no unexplained unconnected nets, reviewed
clearance/thermal/RF behaviour and consistent schematic/PCB connectivity.

## 9. Phase F — Firmware integration and variant checks

Prepare the hardware configuration alongside the PCB: pin assignments, startup
states, transceiver enables, modem control and programming recovery must match.
Preserve the existing VESC CAN control contract initially; ensure exactly one
publisher and retain motor-side stale-control shutdown. Test reset with a held
start button so recovery does not unexpectedly re-enable traction.

Use the existing N1S captures/emulator as fixtures for node 0x20 response testing.
Verify speed scaling and status semantics before claiming complete display support.
NQiX starts listen-only until its protocol is understood. Hardware provisioning
does not satisfy the NQiX functional acceptance criterion.

Define N1S/NQiX population and harness variants explicitly. Confirm that the
variant's termination, input circuitry and NIU supply setpoint match its evidence.
SoC must describe the actual traction battery, not the regulated OEM supply rail.

**Exit:** a hardware/firmware interface document plus bench results for supported
functions; unsupported NQiX functions remain clearly identified.

## 10. Phase G — CI, prototype package and hardware validation

CI performs a clean locked-dependency build, circuit checks, variant connectivity
tests, renders and exports. Include meaningful assertions: no direct raw-pack-to-
NIU-supply connection, independent CAN domains, correct connector mapping, required
MCU grounds, and no accidental USB power backfeed. A netlist check cannot prove
fault behaviour of a MOSFET or regulator; retain those in electrical review/tests.

For each candidate revision archive TSX/source revision, Circuit JSON, schematic
and board views, supported 3D/KiCad exports, BOM, placement data, Gerbers/drills,
stackup/assembly notes and validation report. Inspect the manufacturing files in
an independent viewer and confirm units, origin, side and component rotations.

Mark outputs as a prototype until bench evidence exists. Validate in sequence:
low-voltage supply and recovery; HV converter with dummy loads; protection and
load transients; buses and controls; N1S integration; NQiX integration; WiFi and
SIM VESC Tool access; thermal operation in the intended enclosure. A modem crash
or lost network must not disrupt vehicle control. Prototype ordering is a separate
user action, not an automatic consequence of a successful CI build.

**Exit:** reproducible manufacturing package and recorded prototype results.
Fabrication checks alone do not establish vehicle compatibility.

## 11. Agent execution rules and completion criteria

- Implement concrete TSX circuits and generated previews as milestones; documentation
  alone does not count as PCB implementation.
- Treat existing design notes as inputs to verify. Do not inherit the legacy PCB's
  ground-net mistakes or schematic/PCB mismatch.
- Keep unsupported values explicit. Continue independent work when one measurement
  is missing and report exactly which circuit cannot yet be completed.
- Use stable component references and deterministic source generation. Do not
  silently substitute a different footprint or lower-rated part to satisfy stock.
- Commit coherent reviewed blocks with build results and images. Update a milestone
  checklist with evidence rather than marking a phase complete based on intent.
- Keep the source and manufacturing outputs traceable to the same revision.

The design is complete when both requested vehicle variants have verified
connectors/electrical behaviour, the integrated supply supports measured loads
over the battery range, VESC Tool works over WiFi and SIM, control fault behaviour
is demonstrated, and the routed board/manufacturing package passes the applicable
checks. Until NQiX bench testing passes, describe it as provisioned or experimental.

Immediate implementation milestone: establish the TSCircuit fixture and CI, then
build the gateway/CAN/RS485 low-voltage blocks while obtaining the missing power
and connector measurements. Do not begin with a fully autorouted guessed board.
