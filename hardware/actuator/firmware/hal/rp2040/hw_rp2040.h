/* RP2040 port of the arm_hw interface and the BHMS-Compact HAL (USB CDC transport, E-stop
 * latch from an IRQ, flash-backed epoch). Thread-safety: single owner (core 0 main loop); the
 * GPIO IRQ handler only touches the two latch flags and SERVO_EN. */
#ifndef HW_RP2040_H
#define HW_RP2040_H

#include "arm_hw.h"
#include "bhms.h"

/* Configure every pin to its reset-safe state first (rail off, tool off, bus driver off), then
 * bring up UART0 (1 Mbps), I2C0 + INA219, the ADC, the status LED and the E-stop IRQ. Returns
 * 0, or nonzero when the INA219 did not answer (the arm then refuses to enable: no rail
 * measurement, no rail). */
int hw_init(void);
const arm_hw *hw_arm(void);
/* The BHMS HAL: USB CDC transport, millis, E-stop pin latch, flash epoch. */
const bhms_hal *hw_bhms(void);
/* Open the epoch and calibration regions; call before arm_init / bhms_init. */
void hw_epoch_init(void);
/* Start the hardware watchdog (after initialisation) and feed it. hw_feed is called once per
 * main-loop pass, after a complete arm_device_poll, and nowhere else. */
void hw_watchdog_start(void);
void hw_feed(void);
/* Blink the status LED red forever (initialisation failed); the rail stays off. */
void hw_halt(void) __attribute__((noreturn));

#endif
