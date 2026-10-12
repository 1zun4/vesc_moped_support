#!/usr/bin/env python3
"""
Off-bus transmit / loopback test for the USB-RS485 dongle.

Run with the dongle DISCONNECTED from the scooter bus (A/B open). Many half-duplex
RS485 dongles keep their receiver enabled during transmit, so they echo their own
output -- if we see our bytes come back, the driver is physically working. We try
every plausible direction-control scheme (auto, RTS hi/lo, DTR hi/lo) so a manual-
direction dongle gets a fair shot too.

  ECHO on some mode  -> the driver works; the on-bus failure is elsewhere.
  NO echo anywhere   -> driver likely dead / receiver muted; needs a meter or a
                        second adapter to be 100% sure (see notes printed at end).
"""
import sys
import time

import serial

PORT = "/dev/ttyUSB0"
BAUD = 9600
PROBE = bytes.fromhex("68 99 66 68 5a a5 99 16".replace(" ", ""))   # unique, not a real frame
MARK = bytes.fromhex("689966")


def attempt(ser, label, pre=None, hold=False):
    """pre: (line, level) to set before TX; hold=True keeps it for the whole burst."""
    ser.reset_input_buffer()
    if pre:
        setattr(ser, pre[0], pre[1])
        time.sleep(0.01)
    got = bytearray()
    for _ in range(6):
        ser.write(PROBE)
        ser.flush()
        if not hold and pre:                 # pulse back to RX between frames
            time.sleep(len(PROBE) * 10 / BAUD + 0.002)
            setattr(ser, pre[0], not pre[1])
        time.sleep(0.03)
        got.extend(ser.read(ser.in_waiting or 0))
        if pre and not hold:
            setattr(ser, pre[0], pre[1])
    if pre:                                  # restore
        setattr(ser, pre[0], not pre[1])
    echoed = MARK in bytes(got)
    print(f"  {label:<22} echo={'YES ✅' if echoed else 'no '}   rx={bytes(got).hex(' ')[:48]}")
    return echoed


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0)
    print(f"# off-bus TX test on {PORT}. Probe = {PROBE.hex(' ')}")
    print("# (run with dongle DISCONNECTED from the scooter bus)\n")
    any_echo = False
    any_echo |= attempt(ser, "auto (no toggle)")
    any_echo |= attempt(ser, "RTS=high (pulsed)", ("rts", True), hold=False)
    any_echo |= attempt(ser, "RTS=low (pulsed)", ("rts", False), hold=False)
    any_echo |= attempt(ser, "RTS=high (held)", ("rts", True), hold=True)
    any_echo |= attempt(ser, "RTS=low (held)", ("rts", False), hold=True)
    any_echo |= attempt(ser, "DTR=high (held)", ("dtr", True), hold=True)
    any_echo |= attempt(ser, "DTR=low (held)", ("dtr", False), hold=True)
    ser.close()
    print()
    if any_echo:
        print("RESULT: the dongle DID echo -> its RS485 driver physically works.")
        print("        So on-bus TX failure is elsewhere (load/contention/timing).")
    else:
        print("RESULT: NO echo in any mode. Either the transmit driver isn't working,")
        print("        or this dongle mutes its receiver during TX (so can't echo).")
        print("        To be 100% sure: (a) a multimeter across A/B should swing while")
        print("        transmitting if the driver works, or (b) a 2nd USB-serial/RS485")
        print("        adapter listening would see the frames. Otherwise: replace dongle.")


if __name__ == "__main__":
    main()
