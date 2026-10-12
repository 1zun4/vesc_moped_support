#!/usr/bin/env python3
"""
Full NIU N1S controller (node 0x20) emulator -- with the start-up handshake.

The ECU only trusts the controller after a boot handshake (cmd01/05/06 -> 81/85/86),
captured byte-for-byte from the real controller. This tool replays that handshake,
then answers the steady cmd02 poll with telemetry in which we INJECT speed
(signed 16-bit at decoded payload positions 8-9). Once the ECU accepts us, it
forwards speed to the dashboard's 10EF 04 display frame (km/h at decoded pos 3).

It can also impersonate the battery (node 0x31, SoC) and -- crucially -- it WATCHES
the 10EF 04 display frame while it runs, so it self-reports the display speed/battery
that result from our injected values (calibration without needing to see the screen).

To get past the handshake the real controller must be UNPLUGGED and this running
BEFORE you switch the ignition on.

DEFAULT IS DRY-RUN. Pass --transmit to go live.

Speed source (raw controller units; the ECU scales raw->km/h, calibrate with sweep):
  --speed-raw N     fixed raw speed
  --sweep MAX       triangle 0 -> MAX -> 0 (raw)
  --probe V1,V2,..  cycle raw values (hold --hold s each) for calibration
"""
import argparse
import sys
import time
from collections import deque

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from parse import build_frame, parse_stream, decode_payload  # noqa: E402
from simulate import battery_frame                            # noqa: E402

PORT = "/dev/ttyUSB0"
BAUD = 9600

# --- exact captured handshake: ECU poll -> controller reply (replayed verbatim) ---
HANDSHAKE = {
    bytes.fromhex("6820df680101360716"):
        bytes.fromhex("6820df688110808164676a766475676664686367656a1716"),
    bytes.fromhex("6820df680101370816"):
        bytes.fromhex("6820df68810149 9a16".replace(" ", "")),
    bytes.fromhex("6820df680502 7a70 c016".replace(" ", "")):
        bytes.fromhex("6820df68850101 5616".replace(" ", "")),
    bytes.fromhex("6820df68060144 1a16".replace(" ", "")):
        bytes.fromhex("6820df688600 5516".replace(" ", "")),
}
CTRL02_POLL = bytes.fromhex("6820df680202383b4616")          # -> telemetry w/ speed
BMS_POLL = bytes.fromhex("6831ce680202604275 16".replace(" ", ""))
CTRL_TMPL = bytes.fromhex("6f678d3433" "5e" "33333333" "bbb3")  # on-wire 12B telemetry


def ctrl82(speed_raw):
    """Controller telemetry with signed-16 speed injected at decoded pos 8-9."""
    dec = bytearray(decode_payload(CTRL_TMPL))
    s = int(speed_raw) & 0xFFFF
    dec[8] = (s >> 8) & 0xFF
    dec[9] = s & 0xFF
    wire = bytes((b + 0x33) & 0xFF for b in dec)
    return build_frame(0x20, 0xDF, 0x82, wire, preamble=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--speed-raw", type=int, default=0)
    ap.add_argument("--sweep", type=int, default=None, help="triangle 0->MAX->0 raw")
    ap.add_argument("--sweep-secs", type=float, default=8.0)
    ap.add_argument("--probe", default=None, help="cycle raw speeds, comma list")
    ap.add_argument("--hold", type=float, default=3.0)
    ap.add_argument("--soc", type=int, default=None, help="also emulate BMS at this SoC%%")
    ap.add_argument("--bms-only", action="store_true",
                    help="answer ONLY the BMS poll (real controller stays connected)")
    ap.add_argument("--rts", choices=["auto", "high", "low"], default="auto",
                    help="RS485 direction: auto=adapter handles it; high/low=toggle RTS for TX")
    args = ap.parse_args()

    probe = [int(v) for v in args.probe.split(",")] if args.probe else None

    def speed_raw(t):
        if probe:
            return probe[int(t / args.hold) % len(probe)]
        if args.sweep is not None:
            ph = (t % (2 * args.sweep_secs)) / args.sweep_secs
            return int(ph * args.sweep if ph <= 1 else (2 - ph) * args.sweep)
        return args.speed_raw

    if not args.transmit:
        print("# DRY-RUN. Handshake table + sample telemetry:")
        for poll, resp in HANDSHAKE.items():
            print(f"  {poll.hex(' ')}  ->  {resp.hex(' ')}")
        print(f"  cmd02 -> {ctrl82(0).hex(' ')}  (speed raw 0)")
        print(f"  cmd02 -> {ctrl82(200).hex(' ')}  (speed raw 200)")
        if args.soc is not None:
            print(f"  bms   -> {battery_frame(args.soc).hex(' ')}  (SoC {args.soc})")
        return

    import serial
    from collections import Counter
    ser = serial.Serial(args.port, BAUD, timeout=0)
    # try kernel low-latency mode (reduce CH340 RX buffering) -- best effort
    try:
        import fcntl, array
        TIOCGSERIAL, TIOCSSERIAL = 0x541E, 0x541F
        ss = array.array('i', [0] * 64)
        fcntl.ioctl(ser.fd, TIOCGSERIAL, ss, True)
        ss[4] |= (1 << 13)          # ASYNC_LOW_LATENCY in flags
        fcntl.ioctl(ser.fd, TIOCSSERIAL, ss)
        print("# low-latency mode set")
    except Exception as e:
        print(f"# low-latency not set ({e})")
    # manual RS485 direction via RTS (kernel rs485_mode unsupported on ch341):
    #   rts_tx = the RTS level that puts the transceiver in TRANSMIT.
    rts_tx = {"high": True, "low": False, "auto": None}[args.rts]
    if rts_tx is not None:
        ser.rts = not rts_tx            # idle = receive
        print(f"# manual RTS direction: drive RTS={args.rts} during TX")

    def send(frame):
        if rts_tx is None:
            ser.write(frame); ser.flush()
            return
        ser.rts = rts_tx                # enable driver
        ser.write(frame); ser.flush()   # flush = tcdrain (waits for shift-out)
        time.sleep(len(frame) * 10 / BAUD + 0.0015)  # margin for chip FIFO
        ser.rts = not rts_tx            # back to receive

    buf = bytearray()
    watch = bytearray()
    answered = Counter()           # per-step: cmd01a/cmd01b/cmd05/cmd06/ctrl02/bms
    seen = Counter()               # ECU REQ polls seen (to judge boot/stuck)
    unmatched = deque(maxlen=8)
    disp = {"speed": None, "frame": None, "alive": 0}
    t0 = time.perf_counter()
    last_report = t0
    last_parse = t0
    print(f"# emulate controller (+BMS {args.soc if args.soc is not None else 'off'}) "
          f"LIVE. Power-cycle the ignition now. Ctrl-C to stop.")
    try:
        while args.seconds is None or time.perf_counter() - t0 < args.seconds:
            now = time.perf_counter()
            n = ser.in_waiting
            if n:
                data = ser.read(n)
                buf.extend(data)
                watch.extend(data)
                if len(buf) > 96:
                    del buf[:-96]
                fired = False
                if not args.bms_only:                  # controller emulation
                    for poll, resp in HANDSHAKE.items():
                        if buf.endswith(poll):
                            send(resp)
                            answered["hs"] += 1
                            buf.clear(); fired = True
                            break
                    if not fired and buf.endswith(CTRL02_POLL):
                        send(ctrl82(speed_raw(now - t0)))
                        answered["ctrl02"] += 1
                        buf.clear(); fired = True
                if not fired and args.soc is not None and buf.endswith(BMS_POLL):
                    send(battery_frame(args.soc))
                    answered["bms"] += 1
                    buf.clear()
            else:
                time.sleep(0.0005)
            # watch display + track ECU boot state
            if now - last_parse > 0.2 and watch:
                last_parse = now
                for f in parse_stream(bytes(watch)):
                    if f["addr"] == 0x10EF and f["cmd"] == 0x04:
                        d = decode_payload(f["payload"])
                        disp["speed"] = d[3] if len(d) > 3 else None
                        disp["frame"] = d.hex(" ")
                        disp["alive"] += 1
                    if not (f["cmd"] & 0x80):                       # an ECU poll
                        if f["addr"] == 0x20DF and f["cmd"] == 0x01:
                            seen["cmd01_t"] = now                   # still handshaking
                        if f["addr"] == 0x708F:
                            seen["708f_t"] = now                    # full running bus
                        core = f["raw"][f["preamble"]:]
                        if f["addr"] == 0x20DF and core != CTRL02_POLL and core not in HANDSHAKE:
                            unmatched.append(core.hex(" "))
                del watch[:-48]
            if now - last_report > 2.0:
                last_report = now
                hs_active = (now - seen.get("cmd01_t", -9)) < 2.5
                running = (now - seen.get("708f_t", -9)) < 2.5
                state = ("STUCK: ECU still sending cmd01 handshake" if hs_active
                         else ("BOOTED: full bus running" if running else "?"))
                print(f"  t={now-t0:5.1f}s ans(hs={answered['hs']},ctrl02={answered['ctrl02']},"
                      f"bms={answered['bms']})  display.speed(pos3)={disp['speed']} "
                      f"inject_raw={speed_raw(now-t0)}  [{state}]")
                if unmatched:
                    print(f"    !! unmatched controller polls: {list(unmatched)}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
    print(f"# done. answered={answered}  last display frame={disp['frame']}")


if __name__ == "__main__":
    main()
