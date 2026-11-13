/* BHMS Arm: the hardware abstraction the portable core runs on. The RP2040 port
 * (hal/rp2040) and the host simulator (sim/) each supply one const arm_hw.
 * Hooks are bounded; none may call back into the core.
 * Thread-safety: single owner (the main loop). estop_take_edge is the one hook whose
 * backing flag is written from an interrupt; the port must make that access atomic. */
#ifndef ARM_HW_H
#define ARM_HW_H

#include <stddef.h>
#include <stdint.h>

#include "arm_params.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ADC channels (12-bit, 3.3 V reference). */
enum { ARM_ADC_TOOL_ID = 0, ARM_ADC_TOOL_AUX1 = 1, ARM_ADC_TOOL_AUX2 = 2, ARM_ADC_VIN = 3 };

/* Tri-colour status LED (INTERFACE.md section 7): non-zero = on. */
typedef struct arm_hw {
    void *ctx;
    uint32_t (*millis)(void *ctx);

    /* ---- Half-duplex servo bus (INTERFACE.md section 3). The port owns the driver
     * enable: bus_write drives BUS_TXEN_N low, writes, waits for the UART TX-complete
     * event, and releases the driver before returning. The RX buffer sees the echo. */
    void (*bus_flush)(void *ctx);                      /* discard pending RX bytes */
    void (*bus_write)(void *ctx, const uint8_t *buf, size_t n);
    /* Read up to n bytes; waits at most timeout_us for each missing byte. Returns the
     * number of bytes read (less than n on timeout). */
    size_t (*bus_read)(void *ctx, uint8_t *buf, size_t n, uint32_t timeout_us);

    /* ---- Power and E-stop GPIO (INTERFACE.md sections 2 and 4). */
    void (*servo_en)(void *ctx, int on);   /* GPIO6 */
    void (*tool_en)(void *ctx, int on);    /* GPIO7 */
    int (*estop_sense)(void *ctx);         /* GPIO8: 1 = pressed / open / unplugged */
    /* Latched rising edge of GPIO8 (set from the IRQ, which has already cleared SERVO_EN);
     * returns nonzero once per edge and clears it. */
    int (*estop_take_edge)(void *ctx);

    uint16_t (*adc_read)(void *ctx, uint8_t channel);

    /* INA219 raw registers: bus voltage (0x02) and current (0x04). Returns 0 on success. */
    int (*ina_read)(void *ctx, uint16_t *bus_reg, int16_t *current_reg);

    void (*led)(void *ctx, uint8_t r, uint8_t g, uint8_t b);

    /* ---- Optional (NULL when the platform has none). */
    /* Nonzero when the last reset was caused by the watchdog. */
    int (*watchdog_reset)(void *ctx);
    /* Persistent joint calibration: load returns 1 when a stored calibration exists. save
     * returns 0 once it is durable; it may mask interrupts for tens of ms, so the core calls it
     * only with the servo rail off. */
    int (*cal_load)(void *ctx, arm_cal *cal);
    int (*cal_save)(void *ctx, const arm_cal *cal);
} arm_hw;

#ifdef __cplusplus
}
#endif
#endif
