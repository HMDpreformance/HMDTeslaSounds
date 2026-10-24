// HMD Sounds pedal dongle: ESP32 + CAN transceiver on a Tesla Model 3/Y diagnostic port.
// It only LISTENS to the car's CAN bus (never transmits), reads the accelerator pedal from
// message 0x118 (DI_systemStatus, byte 4, 0.4 %/bit), and publishes it over Wi-Fi to MQTT topic
// hmdsound/<PEDAL_CODE>/pedal. In the app, type the same code under Settings -> Pedal link.
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
uint32_t lastSend = 0, lastFrame = 0;

void canStart() {
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX, CAN_RX, TWAI_MODE_LISTEN_ONLY);
  g.rx_queue_len = 64;
  twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
  // hardware filter: only accept ID 0x118
  twai_filter_config_t f = { .acceptance_code = (0x118u << 21), .acceptance_mask = ~(0x7FFu << 21), .single_filter = true };
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
    }
  }
  if (!mqtt.connected()) { static uint32_t retry = 0; if (millis() - retry > 2000) { retry = millis(); netUp(); } }
  mqtt.loop();
  uint32_t now = millis();
  // send on change at up to 30 Hz, and a keep-alive every 250 ms so the app knows the link is live
  bool fresh = pedal >= 0 && now - lastFrame < 500;
  if (fresh && mqtt.connected() && now - lastSend >= 33 && (pedal != sent || now - lastSend >= 250)) {
    char buf[8]; snprintf(buf, sizeof buf, "%d", pedal);
    mqtt.publish(topic, buf);
    sent = pedal; lastSend = now;
    Serial.printf("pedal %d%%\n", pedal);
  }
}
