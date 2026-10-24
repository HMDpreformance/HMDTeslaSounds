#!/usr/bin/env python3
"""HMD Sounds pedal + speed bridge for a laptop with a USB-CAN adapter (CANable / candleLight / slcan).

Listens (never transmits) on the Model 3 vehicle CAN bus, reads:
  0x118 DI_systemStatus  byte 4  -> accelerator pedal, 0.4 %/bit
  0x257 DI_speed         bits 12..23 -> vehicle speed, 0.08 km/h/bit, -40 offset
and publishes "pedal,speed" to MQTT topic hmdsound/<code>/pedal at up to 30 Hz.

  pip install python-can paho-mqtt
  python3 hmd_pedal_laptop.py --code hamad1                         # candleLight / gs_usb (Linux: socketcan can0)
  python3 hmd_pedal_laptop.py --code hamad1 --iface slcan --channel COM5   # slcan firmware (Windows COM port)
  python3 hmd_pedal_laptop.py --sniff                               # just print raw 0x118/0x257 frames
"""
import argparse, time
import can

ap = argparse.ArgumentParser()
ap.add_argument("--code", default="hamad1")
ap.add_argument("--iface", default="gs_usb", help="gs_usb | slcan | socketcan | pcan ...")
ap.add_argument("--channel", default=None, help="e.g. can0, COM5, /dev/ttyACM0")
ap.add_argument("--bitrate", type=int, default=500000)
ap.add_argument("--broker", default="broker.hivemq.com")
ap.add_argument("--sniff", action="store_true")
a = ap.parse_args()

kw = {"interface": a.iface, "bitrate": a.bitrate}
if a.channel: kw["channel"] = a.channel
elif a.iface == "socketcan": kw["channel"] = "can0"
elif a.iface == "gs_usb": kw.update(channel=0, index=0)
if a.iface in ("gs_usb", "slcan"): kw["receive_own_messages"] = False
bus = can.Bus(**kw, can_filters=[{"can_id": 0x118, "can_mask": 0x7FF}, {"can_id": 0x257, "can_mask": 0x7FF}])

mq = None
if not a.sniff:
    import paho.mqtt.client as mqtt
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"hmdpedal-laptop-{int(time.time())%100000}")
    mq.connect(a.broker, 1883, keepalive=30); mq.loop_start()
topic = f"hmdsound/{a.code}/pedal"
print("listening on", kw, "->", "sniff" if a.sniff else topic)

pedal, speed, sent, sent_spd, last = None, None, None, None, 0.0
while True:
    m = bus.recv(timeout=0.5)
    if m is not None:
        d = m.data
        if a.sniff:
            print(f"{m.arbitration_id:03X}  {d.hex(' ')}"); continue
        if m.arbitration_id == 0x118 and len(d) >= 5:
            pedal = min(100, round(d[4] * 0.4))
        elif m.arbitration_id == 0x257 and len(d) >= 3:
            raw = ((d[1] >> 4) | (d[2] << 4)) & 0xFFF
            speed = max(0.0, raw * 0.08 - 40)
    now = time.time()
    if pedal is not None and now - last >= 0.033 and (pedal != sent or (speed or 0) != (sent_spd or 0) or now - last >= 0.25):
        msg = f"{pedal},{speed:.1f}" if speed is not None else f"{pedal}"
        mq.publish(topic, msg, qos=0)
        sent, sent_spd, last = pedal, speed, now
        print(f"\rpedal {pedal:3d}%  speed {speed if speed is not None else 0:6.1f} km/h ", end="", flush=True)
