# Audit of the existing board

Inspected baseline: `81464eb3128a81d19698f908b49b5e8251b3c8fe`, branch
`feat/vesc-link`. Findings below are source inspection, not an ERC/DRC run.

1. **Schematic and PCB differ.** Schematic-only references are D1, D2, J4, J5,
   J6, J7, R1, R2, R5, U1 and U7. In particular U1 is `PQDE6W-Q110` and U7 is
   `PC817`. The PCB does not implement all the schematic's power/interface parts.
   Reconcile intentionally omitted parts versus stale PCB before any reuse.
2. **MCU ground nets need review.** In the PCB U2 VSSA is explicitly unconnected;
   several digital VSS pads use `Net-(U2-VSS-Pad23)` rather than the `GND` net.
   These are net-assignment findings; copper connectivity has not been simulated.
   All required grounds must be explicitly connected and verified in the new design.
3. **Harness input levels are unproven.** Named MODE/ACC_LOCK/BRAKE_LAMP/EABS/
   SIDE_STAND/CRUISE nets appear at MCU pins. Names do not establish voltage
   compatibility. Add conditioned interfaces only after measuring each signal.
4. **Throttle divider needs headroom review.** Existing values 33k series and
   68k to ground yield 3.366 V at an ideal 5 V input. This exceeds nominal 3.3 V
   full scale even before tolerance; it is not proof of damage under the actual
   throttle range. Verify maximum signal and tolerances and add input protection.
5. **RS485 termination is fixed in the PCB.** R9 is 120 ohm across RS485 A/B.
   The new design makes termination configurable to suit the actual bus topology.
6. **The existing CAN port is one bus.** A second independent controller channel
   and transceiver are needed to bridge NIU CAN without mixing it with VESC CAN.
7. **Firmware is not a VL Link drop-in.** `code_esp.lbm` stops the u-blox driver
   and uses GPIO20/21 for an expander. Allocate connectivity pins afresh.

`legacy_connector.csv` is extracted from J1's PCB pads. It intentionally preserves
unconnected and unnamed nets. Never treat this table as a verified OEM pinout.

Run `python hardware/niu_link/tools/audit_legacy.py` to reproduce the component
difference, J1 assignments and U2 ground assignments directly from the sources.
