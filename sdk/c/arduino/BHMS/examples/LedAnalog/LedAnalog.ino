// BHMS-Compact device: an LED action and an analog-read property.
// Description sidecar: led_analog.sidecar.json (digest8 from tools/bhms_digest.py).
#include <BHMSDevice.h>
#include "led_analog_digest.h"  // generated: tools/bhms_digest.py --header

static uint8_t writes;
static uint8_t ledRun(void *, const bhms_value *a, bhms_call *c) {
  digitalWrite(LED_BUILTIN, a[0].u ? HIGH : LOW);
  c->results[0].u = ++writes;
  return BHMS_RUN_DONE;
}
static uint8_t adcRead(void *, uint8_t, bhms_value *v, bhms_sample *) {
  v->u = analogRead(A0);
  return BHMS_Q_VALID;
}
BHMS_FIELDS(ledIn) = {BHMS_BOOL()};
BHMS_FIELDS(ledOut) = {BHMS_U8()};
static const bhms_action actions[] BHMS_PROGMEM = {
    BHMS_ACTION(ledRun, 0, 0, BHMS_FIELDS_REF(ledIn), BHMS_FIELDS_REF(ledOut))};
static const bhms_property props[] BHMS_PROGMEM = {BHMS_PROPERTY(adcRead, BHMS_U16)};
static const bhms_device dev = {
    BHMS_DIGEST8, 0, actions, 1, props, 1, 0, 0};
BHMSDevice bhms(Serial, dev);

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  if (bhms.begin() != BHMS_OK)  // bad capability table: never run, blink fast
    for (;;) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(100); }
}
void loop() { bhms.poll(); }
