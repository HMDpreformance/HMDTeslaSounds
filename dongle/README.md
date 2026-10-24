# HMD Sounds pedal dongle

This makes the app follow your real accelerator pedal. GPS still gives the speed, and the dongle gives the throttle. If the dongle drops out, the app switches back to the GPS throttle estimate on its own.

## Parts (about $20-40)
- An ESP32 dev board (any ESP32 with Wi-Fi; it has a CAN controller built in)
- An SN65HVD230 CAN transceiver module (3.3 V)
- A Tesla Model 3/Y diagnostic-port to OBD2 adapter cable (the 20-pin connector behind the centre console)
- A USB power lead for the ESP32 (from a car USB port)

## Wiring
| ESP32 | SN65HVD230 | Car (OBD2 side of the adapter) |
|---|---|---|
| 3V3 | 3V3 | |
| GND | GND | pin 4/5 (ground) |
| GPIO 5 | CTX / TXD | |
| GPIO 4 | CRX / RXD | |
| | CANH | pin 6 |
| | CANL | pin 14 |

Most adapter cables put the vehicle CAN bus on OBD pins 6/14, but check your cable's pinout. The pedal message (0x118) is on the vehicle bus.

## Flashing
1. Install Arduino IDE, add the ESP32 boards package, and install the **PubSubClient** library.
2. Open `hmd_pedal/hmd_pedal.ino`. Set your phone hotspot's name and password, and pick a `PEDAL_CODE` (for example `hamad1`).
3. Upload it, then open the Serial Monitor at 115200. With the car awake, pressing the pedal should print `pedal 0%` to `pedal 100%`.

## In the app
Go to Settings → **Pedal link**, type the same code, and press **Connect**. The top bar shows `Pedal 45%` while it's live. The app remembers the code.

## Notes
- The ESP32 runs in listen-only mode, so it never sends anything on the car's bus.
- Data goes through the free public broker `broker.hivemq.com`. It only carries a 0-100 number on your code's topic, so use a code nobody else would guess.
- These CAN IDs are for the Model 3/Y. A Model S/X uses different messages.
