#!/usr/bin/env python3
"""HMD Sounds pedal + speed bridge using an ordinary ELM327-style OBD2 adapter (USB, Bluetooth or Wi-Fi).

Uses the adapter's CAN monitor mode (ATMA) with a receive filter, so it only LISTENS on the bus:
  0x118 DI_systemStatus  byte 4      -> accelerator pedal, 0.4 %/bit
  0x257 DI_speed         bits 12..23 -> speed, 0.08 km/h/bit, -40 offset
and publishes "pedal,speed" to MQTT topic hmdsound/<code>/pedal for the app's Pedal link.

  pip install pyserial paho-mqtt
  python3 hmd_pedal_elm.py --code hamad1 --port COM5             # USB or Bluetooth (paired, shows as a COM / /dev/tty.* port)
  python3 hmd_pedal_elm.py --code hamad1 --tcp 192.168.0.10:35000 # Wi-Fi ELM (laptop needs internet another way, e.g. phone USB tether)
  python3 hmd_pedal_elm.py --port COM5 --sniff                    # print raw frames only
  add --pedal-only for the fastest pedal updates (speed then comes from GPS)

Cheap ELM clones are slow at switching filters; expect ~5-10 pedal updates/s, or ~20-30/s with --pedal-only.
"""
import argparse, socket, time

ap = argparse.ArgumentParser()
ap.add_argument("--code", default="hamad1")
ap.add_argument("--port", help="serial port, e.g. COM5 or /dev/tty.OBDII-SPPDev or /dev/ttyUSB0")
ap.add_argument("--baud", type=int, default=38400)
ap.add_argument("--tcp", help="host:port for Wi-Fi adapters")
ap.add_argument("--broker", default="broker.hivemq.com")
ap.add_argument("--pedal-only", action="store_true")
ap.add_argument("--sniff", action="store_true")
a = ap.parse_args()

class Link:
    def __init__(self):
        if a.tcp:
            h, p = a.tcp.split(":"); self.s = socket.create_connection((h, int(p)), timeout=2); self.ser = None
        else:
            import serial; self.ser = serial.Serial(a.port, a.baud, timeout=0.05); self.s = None
        self.buf = b""
    def write(self, b): (self.ser.write(b) if self.ser else self.s.sendall(b))
    def read(self):
        try:
            return self.ser.read(256) if self.ser else self.s.recv(256)
        except socket.timeout:
            return b""
    def lines(self, until_prompt=False, timeout=1.0):
        """yield text lines; stop at the '>' prompt (or timeout)"""
        end = time.time() + timeout
        while time.time() < end:
            if self.s: self.s.settimeout(max(0.01, end - time.time()))
            self.buf += self.read()
            while b"\r" in self.buf:
                ln, self.buf = self.buf.split(b"\r", 1)
                ln = ln.strip().decode(errors="ignore")
                if ln: yield ln
            if b">" in self.buf:
                self.buf = self.buf.split(b">", 1)[1]; return
    def cmd(self, c, timeout=1.5):
        self.write((c + "\r").encode()); return list(self.lines(timeout=timeout))

elm = Link()
for c in ["ATZ", "ATE0", "ATL0", "ATS0", "ATH1", "ATSP6", "ATCAF0", "ATAL"]:
    r = elm.cmd(c, 3 if c == "ATZ" else 1.5); print(c, r)

mq = None
if not a.sniff:
    import paho.mqtt.client as mqtt
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"hmdpedal-elm-{int(time.time())%100000}")
    mq.connect(a.broker, 1883, keepalive=30); mq.loop_start()
topic = f"hmdsound/{a.code}/pedal"
pedal = speed = None

def parse(ln):
    global pedal, speed
    ln = ln.replace(" ", "")
    if len(ln) < 5 or not all(ch in "0123456789ABCDEFabcdef" for ch in ln): return
    cid, d = int(ln[:3], 16), bytes.fromhex(ln[3:] if len(ln[3:]) % 2 == 0 else ln[3:-1])
    if a.sniff: print(f"{cid:03X}  {d.hex(' ')}"); return
    if cid == 0x118 and len(d) >= 5: pedal = min(100, round(d[4] * 0.4))
    elif cid == 0x257 and len(d) >= 3: speed = max(0.0, (((d[1] >> 4) | (d[2] << 4)) & 0xFFF) * 0.08 - 40)

def monitor(cid, frames, window):
    elm.cmd("ATCRA" + cid, 1)
    elm.write(b"ATMA\r"); got, end = 0, time.time() + window
    for ln in elm.lines(timeout=window):
        parse(ln); got += 1
        if got >= frames or time.time() > end: break
    elm.write(b"\r"); list(elm.lines(timeout=0.5))  # any key stops ATMA

print("streaming ->", "sniff" if a.sniff else topic)
while True:
    if a.pedal_only:
        elm.cmd("ATCRA118", 1); elm.write(b"ATMA\r")
        last = 0
        for ln in elm.lines(timeout=3600):
            parse(ln)
            if mq and pedal is not None and time.time() - last >= 0.033:
                mq.publish(topic, f"{pedal}"); last = time.time()
                print(f"\rpedal {pedal:3d}% ", end="", flush=True)
        elm.write(b"\r"); list(elm.lines(timeout=0.5)); continue
    monitor("118", 4, 0.25)
    monitor("257", 1, 0.25)
    if mq and pedal is not None:
        mq.publish(topic, f"{pedal},{speed:.1f}" if speed is not None else f"{pedal}")
        print(f"\rpedal {pedal:3d}%  speed {speed if speed is not None else 0:6.1f} km/h ", end="", flush=True)
