/* Arduino binding for the BHMS-Compact C library (bhms.h).
 *
 * Maps the HAL onto the Arduino core: a Stream (usually Serial), EEPROM for the
 * persistent boot epoch, millis() and an optional stop pin. The wrapper header is
 * not named BHMS.h because that would collide with bhms.h on case-insensitive
 * filesystems.
 *
 * Example (see examples/LedAnalog):
 *   BHMSDevice bhms(Serial, dev);
 *   void setup() { Serial.begin(115200); bhms.begin(); }
 *   void loop()  { bhms.poll(); }
 *
 * Thread-safety: call begin() and poll() from the main loop only.
 */
#ifndef BHMS_DEVICE_H
#define BHMS_DEVICE_H

#include <Arduino.h>
#include <EEPROM.h>

#include "bhms.h"

class BHMSDevice {
public:
    /* port: byte stream to the gateway. dev: the capability table (static).
     * stop_pin: digital input that is the hardware stop, or -1 for none; it is
     * asserted at LOW when stop_active_low (INPUT_PULLUP is configured by begin()).
     * eeprom_addr: first of 4 EEPROM bytes holding the boot counter, or -1 to run
     * without a persistent epoch (PERSISTENT_EPOCH is then not advertised). */
    BHMSDevice(Stream &port, const bhms_device &dev, int8_t stop_pin = -1,
               bool stop_active_low = true, int eeprom_addr = 0)
        : port_(port), dev_(dev), stop_pin_(stop_pin), stop_low_(stop_active_low),
          eeprom_addr_(eeprom_addr) {}

    /* Persist the next boot epoch and arm the endpoint. Returns BHMS_OK or an
     * error if the capability table does not fit the configured bounds. */
    bhms_err begin() {
        hal_.ctx = this;
        hal_.uart_read = &BHMSDevice::uartRead;
        hal_.uart_write = &BHMSDevice::uartWrite;
        hal_.millis = &BHMSDevice::now;
        hal_.stop_pin = stop_pin_ >= 0 ? &BHMSDevice::stopPin : 0;
        hal_.epoch_load = eeprom_addr_ >= 0 ? &BHMSDevice::epochLoad : 0;
        hal_.epoch_store = eeprom_addr_ >= 0 ? &BHMSDevice::epochStore : 0;
        if (stop_pin_ >= 0) pinMode(stop_pin_, stop_low_ ? INPUT_PULLUP : INPUT);
        return bhms_init(&ep_, &dev_, &hal_);
    }

    /* Service the link; call every loop() iteration. */
    void poll() { bhms_poll(&ep_); }

    /* The underlying endpoint, for bhms_op_finish / bhms_publish / bhms_stop_confirmed. */
    bhms_endpoint &endpoint() { return ep_; }

private:
    static BHMSDevice &self(void *ctx) { return *static_cast<BHMSDevice *>(ctx); }
    static int uartRead(void *ctx) { return self(ctx).port_.read(); }
    static void uartWrite(void *ctx, const uint8_t *buf, size_t n) { self(ctx).port_.write(buf, n); }
    static uint32_t now(void *) { return millis(); }
    static int stopPin(void *ctx) {
        BHMSDevice &d = self(ctx);
        return (digitalRead(d.stop_pin_) == LOW) == d.stop_low_;
    }
    static int epochLoad(void *ctx, uint32_t *epoch) {
        uint32_t v = 0;
        EEPROM.get(self(ctx).eeprom_addr_, v);
        *epoch = v == 0xFFFFFFFFul ? 0 : v; /* erased cell */
        return 0;
    }
    static int epochStore(void *ctx, uint32_t epoch) {
        uint32_t back = 0;
        int addr = self(ctx).eeprom_addr_;
        EEPROM.put(addr, epoch); /* writes only changed bytes */
        EEPROM.get(addr, back);
        return back == epoch ? 0 : -1;
    }

    Stream &port_;
    const bhms_device &dev_;
    int8_t stop_pin_;
    bool stop_low_;
    int eeprom_addr_;
    bhms_hal hal_;
    bhms_endpoint ep_;
};

#endif
