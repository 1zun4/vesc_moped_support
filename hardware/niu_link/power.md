# Power design envelope

30S at 4.2 V/cell means 126 V maximum steady battery voltage. Chemistry and the
allowed minimum battery voltage must be confirmed. Regenerative and hot-plug
transients are additional design inputs. The user's 84 V ceiling is a ceiling,
not a selected output setpoint or a substitute for component ratings.

## Separate loads

| Rail | Loads | Sizing input still needed |
| --- | --- | --- |
| NIU_SUPPLY | Original ECU/dashboard and possibly original lighting DC/DC | Actual external converter output; continuous and startup current |
| AUX_12V | Gateway and connectivity downstream regulators | Sum of downstream power and conversion losses |
| MODEM_VBAT | Cellular modem | Hardware-manual burst profile and allowable voltage droop |
| LOGIC_5V / 3V3 | MCU, ESP, transceivers, optional storage | Mode-specific consumption and startup sequencing |

NIU load measurements must include ignition startup, headlight, indicators, horn,
alarm and any accessories actually powered through this rail. A rated 2 A external
converter does not prove that the load draws 2 A.

## Converter trade study

| Candidate approach | Suitable use | Limitation |
| --- | --- | --- |
| LTC3895 synchronous buck | Candidate auxiliary 12 V converter | 140 V operating input, 150 V absolute maximum; requires verified input protection. Output limited to 60 V, so reject for a 72–84 V NIU rail |
| LT8316 flyback | Candidate NIU rail with custom turns ratio; ample controller input range | Transformer, MOSFET reflected voltage, snubber, startup and regulation require design; published low-voltage demo is not a drop-in 72 V design |
| HV buck using external switch/controller suitable for requested output | Candidate NIU rail if common return is acceptable | Must verify high output common-mode and controller supply ratings, not just MOSFET voltage |

Do not release the power BOM until output/load requirements select a topology.
For an isolated flyback, secondary-to-primary connections through vehicle signals
must be explicitly resolved. Its switch stress is input + reflected output +
leakage overshoot, not merely 126 V. A buck's switch and rectifier still require
transient margin. Capacitor selection includes ripple current and temperature.

## Numerical scenarios, not NIU measurements

At 72 V, 0.5 A, and 90% converter efficiency: output = 36 W, input = 40 W,
converter loss = 4 W. At 72 V, 1 A: loss = 8 W. These alone can determine whether
the converter fits the intended sealed enclosure. Connectivity power is additional.

For a hypothetical buck at 126 V input and 72 V output, ideal duty = 0.5714.
At 200 kHz with 0.3 A peak-to-peak ripple, L is approximately 514 microhenry.
This is a calculation example, not a selected inductor: load, saturation, ripple,
core loss, compensation, minimum on/off time and operating modes remain to be sized.

For modem burst buffering, C >= I * dt / deltaV estimates only the capacitor
contribution, excluding ESR and regulator response. A hypothetical 2 A, 1 ms burst
with 0.2 V allowed droop would need 10 mF if the regulator supplied none of that
incremental current. Do not copy a generic capacitor value without this check.

## Protection and parked operation

- Independent NIU overvoltage shutdown must keep the worst-case output below the
  verified ceiling after tolerance, propagation delay and stored energy. Choose
  the normal setpoint lower than the trip threshold; both are hardware-defined.
- Reverse current from retained OEM batteries or charged output capacitance must
  be considered. Do not connect two sources directly together through the harness.
- Startup must support the gateway before the NIU controller handshake. A modem
  burst or crash must not reset the vehicle gateway.
- Default parked mode removes modem power after a controlled shutdown. Optional
  remote mode needs an undervoltage cutoff and a measured average energy budget.
  For illustration only, 0.5 W continuously consumes 12 Wh/day before upstream loss.

Use `tools/power_budget.py` for repeatable scenario calculations. It does not
select protection devices or certify a topology.
