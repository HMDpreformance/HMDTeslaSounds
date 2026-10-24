// HMD Sounds pedal dongle: ESP32 + CAN transceiver on a Tesla Model 3/Y diagnostic port.
// It only LISTENS to the car's CAN bus (never transmits), reads the accelerator pedal from
// message 0x118 (DI_systemStatus, byte 4, 0.4 %/bit) and the car's speed from 0x257
// (DI_vehicleSpeed, 12 bits from bit 12, 0.08 km/h/bit, -40 offset), and publishes "pedal,speed"
// over Wi-Fi to MQTT topic hmdsound/<PEDAL_CODE>/pedal. In the app, type the same code under Settings -> Pedal link.
//
// Board: any ESP32 (built-in TWAI CAN controller) + SN65HVD230 3.3 V transceiver module.
// Libraries: PubSubClient (Nick O'Leary) from the Arduino Library Manager.

#include <WiFi.h>
#include <PubSubClient.h>
#include "driver/twai.h"

// ---- edit these ----
const char* WIFI_SSID = "your-phone-hotspot";
const char* WIFI_PASS = "hotspot-password";
const char* PEDAL_CODE = "hamad1";            // must match the app, lowercase letters/numbers/dashes
const gpio_num_t CAN_TX = GPIO_NUM_5;          // ESP32 pin -> transceiver CTX/TXD
const gpio_num_t CAN_RX = GPIO_NUM_4;          // ESP32 pin -> transceiver CRX/RXD
// --------------------

const char* BROKER = "broker.hivemq.com";
WiFiClient net;
PubSubClient mqtt(net);
char topic[64];
int pedal = -1, sent = -1;
float speed = -1, sentSpeed = -1;   // km/h
uint32_t lastSend = 0, lastFrame = 0;

void canStart() {
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX, CAN_RX, TWAI_MODE_LISTEN_ONLY);
  g.rx_queue_len = 256;
  twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL(); // filtered in software below (0x118 + 0x257)
  twai_driver_install(&g, &t, &f);
  twai_start();
}

void netUp() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  }
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()) {
    char id[32]; snprintf(id, sizeof id, "hmdpedal-%06x", (unsigned)(ESP.getEfuseMac() & 0xFFFFFF));
    mqtt.connect(id);
  }
}

void setup() {
  Serial.begin(115200);
  snprintf(topic, sizeof topic, "hmdsound/%s/pedal", PEDAL_CODE);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                         // low latency
  mqtt.setServer(BROKER, 1883);
  canStart();
  netUp();
}

void loop() {
  twai_message_t m;
  while (twai_receive(&m, 0) == ESP_OK) {
    if (m.identifier == 0x118 && m.data_length_code >= 5) {
      pedal = min(100, (int)(m.data[4] * 0.4f + 0.5f));
      lastFrame = millis();
    } else if (m.identifier == 0x257 && m.data_length_code >= 4) {
      uint32_t raw = ((m.data[1] >> 4) | (m.data[2] << 4)) & 0xFFF;
      speed = max(0.0f, raw * 0.08f - 40.0f);
    }
  }
  if (!mqtt.connected()) { static uint32_t retry = 0; if (millis() - retry > 2000) { retry = millis(); netUp(); } }
  mqtt.loop();
  uint32_t now = millis();
  // send on change at up to 30 Hz, and a keep-alive every 250 ms so the app knows the link is live
  bool fresh = pedal >= 0 && now - lastFrame < 500;
  if (fresh && mqtt.connected() && now - lastSend >= 33 && (pedal != sent || fabsf(speed - sentSpeed) >= 0.3f || now - lastSend >= 250)) {
    char buf[24];
    if (speed >= 0) snprintf(buf, sizeof buf, "%d,%.1f", pedal, speed); else snprintf(buf, sizeof buf, "%d", pedal);
    mqtt.publish(topic, buf);
    sent = pedal; sentSpeed = speed; lastSend = now;
    Serial.printf("pedal %d%%  speed %.1f km/h\n", pedal, speed);
  }
}
