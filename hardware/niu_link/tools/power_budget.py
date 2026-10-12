#!/usr/bin/env python3
"""Ideal steady-state sizing scenarios, not a validated converter design."""
import argparse
import json
import math


def calculate(output_v, output_a, efficiency, input_v=126.0,
              frequency_hz=200000.0, ripple_a=0.3):
    values = (output_v, output_a, efficiency, input_v, frequency_hz, ripple_a)
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("All inputs must be finite and positive")
    if efficiency > 1:
        raise ValueError("Efficiency must be in (0, 1]")
    if output_v >= input_v:
        raise ValueError("Buck scenario requires output voltage below input voltage")
    output_w = output_v * output_a
    input_w = output_w / efficiency
    duty = output_v / input_v
    return {
        "scenario_only": True,
        "input_v": input_v,
        "output_w": output_w,
        "input_w": input_w,
        "loss_w": input_w - output_w,
        "input_a": input_w / input_v,
        "ideal_buck_duty": duty,
        "ideal_buck_inductance_h": (input_v - output_v) * duty / (frequency_hz * ripple_a),
        "ideal_inductor_peak_a": output_a + ripple_a / 2,
        "ccm_assumption_valid": output_a > ripple_a / 2,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-v", type=float, required=True)
    parser.add_argument("--output-a", type=float, required=True)
    parser.add_argument("--efficiency", type=float, required=True)
    parser.add_argument("--input-v", type=float, default=126)
    parser.add_argument("--frequency-hz", type=float, default=200000)
    parser.add_argument("--ripple-a", type=float, default=0.3)
    args = parser.parse_args()
    try:
        result = calculate(**vars(args))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
