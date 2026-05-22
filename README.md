# VESC NIU N1S Control

This is my Lisp-based control package for a NIU N1S running a [VESCLabs Maxim+ 150V](https://www.vesclabs.com/product/vl-maxim-plus-150v/). The setup uses both the ESC side (STM) and VESC Express (ESP).

The ECU already handles the light controls on its own. This package adds controls for the ESC inputs.

## Current Status

Supported now:

It is now supported:

- Goes into the no power profile when started or when the sidestand is down.
- Goes into a custom profile set from the GUI when the start button is pressed and the sidestand is up.
- The left mode button selects reverse mode.
- The right mode button selects normal mode.
- The cruise control can be activated by pressing the cruise button and will remain active until it the button is pressed again, braking, lowering the sidestand or reapplying the throttle.

Still planned:

- NIU N1S display support over a TTL to RS485 adapter

## Wiring Photo

Wiring photo placeholder: I will add the NIU N1S ESC plug to VESCLabs Maxim+ 150V wiring picture soon.

## ADC App Configuration

- Buttons: Enable Cruise

## Reference

Based on the example package: https://github.com/vedderb/vesc_pkg/tree/main/vl_bike_39p
