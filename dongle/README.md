# HMD Sounds pedal dongle

This makes the app follow your real accelerator pedal. GPS still gives the speed, and the dongle gives the throttle. If the dongle drops out, the app switches back to the GPS throttle estimate on its own.

## Parts (about $20-40)
- An ESP32 dev board (any ESP32 with Wi-Fi; it has a CAN controller built in)
- An SN65HVD230 CAN transceiver module (3.3 V)
- A **Model 3 Highland (2024+)** OBD2 / CAN adapter cable. The Highland moved the connector, so older Model 3 cables don't fit. Its harness sits behind the plastic trim next to the driver's door hinge and needs a Highland-specific Y-cable. Search for "Model 3 Highland OBD2 adapter". Make sure the cable breaks out the **vehicle CAN** bus.
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
- Pedal message 0x118 comes from the community Model 3 CAN database. It should still be there on the Highland, but nobody has confirmed it on a 2024 car yet. If the Serial Monitor stays at `pedal 0%` while you press the pedal, send me a screenshot of the output and I'll find the right message.
