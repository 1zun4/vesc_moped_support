# Source register

Consulted 2026-10-12. Component candidates require a final datasheet revision and
ordering-code review before schematic release.

| Source | Design use |
| --- | --- |
| [VESC Link](https://www.vesclabs.com/product/vl-link/) | ESP32-C3/VESC Express, WiFi/BLE, cellular, TCP hub, 3–15 V input |
| [VL Link hardware header](https://github.com/vedderb/vesc_express/blob/main/main/hwconf/vesc/link/hw_link.h) | ESP target and CAN GPIO0/1; not a complete hardware schematic |
| [VESC Express](https://github.com/vedderb/vesc_express) | Custom hardware target and upstream connectivity integration |
| [STM32G0B1RE](https://www.st.com/en/microcontrollers-microprocessors/stm32g0b1re.html) | Two FDCAN controllers; candidate gateway family |
| [TCAN1042HGV-Q1](https://www.ti.com/product/TCAN1042HGV-Q1) | Candidate CAN physical interface; exact suffix review required |
| [LTC3895](https://www.analog.com/en/products/ltc3895.html) | 140 V operating input, 150 V absolute maximum, output up to 60 V |
| [LT8316](https://www.analog.com/en/products/lt8316.html) | Alternative HV converter controller; custom power stage required |
| [N1S protocol](../../protocol_rs485/PROTOCOL.md) | Captured serial settings, node roles, startup and telemetry |
| [N1S emulator](../../protocol_rs485/tools/emulate.py) | Existing captured handshake implementation; no new protocol claims |

OEM NQiX electrical documentation and the actual connector manufacturer drawings
are not yet available in this design. No vendor compatibility claim is made.
