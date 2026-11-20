#ifndef HMS_AVR_CLOCK_H
#define HMS_AVR_CLOCK_H

#include <stdint.h>

/* Original exclusive ATmega328P Timer1 clock, normal mode, 16 MHz / 64.
 * No Arduino Timer0 dependency. Incompatible with Servo, Timer1 PWM/capture,
 * other Timer1 vectors/users, and unannounced shared-prescaler changes.
 * F_CPU is a build assertion, NOT evidence of actual oscillator frequency.
 *
 * INSTALLATION CONTRACT: one static object, one foreground owner, and exactly
 * one call to overflow() from each ordinary (non-nesting) TIMER1_OVF vector,
 * after hardware clears TOV1. No other code reads/writes Timer1's shared TEMP.
 * From start onwards every overflow must be accounted for STRICTLY BEFORE
 * 32768 subsequent raw ticks (nominal 131.072 ms). This includes all interrupt
 * masking, other ISRs, sleep/wakeup, and this module's critical windows. These
 * finite windows have no polling loops; their elapsed time is not measured.
 * A single TOV1 bit cannot detect arbitrary missed wraps: a multiple-wrap gap
 * can alias a timely sample. External scheduling assurance/monitoring is
 * mandatory. Invalidate BEFORE any possible bound violation, clock change,
 * unaccounted sleep, debug halt, Timer1 access or shared-prescaler reset.
 *
 * Init and start are permitted only once in a fresh endpoint boot domain,
 * while effects are inhibited. Never call init to clear a live fault or
 * rebase admitted work. Only a new endpoint boot/inhibit boundary can create
 * another clock object. This library neither persists nor increments epochs.
 * Supplied epochs must already be durable/nonreused; zero and UINT64_MAX
 * are rejected. No recovery, generation change, or clock reset API exists.
 * Objects/output must be valid and nonoverlapping; do not mutate state fields.
 */
#define HMS_AVR_CLOCK_RAW_PER_MS 250u
#define HMS_AVR_CLOCK_SERVICE_LIMIT 32768u
#define HMS_AVR_CLOCK_RAW_MAX UINT64_C(0x0000ffffffffffff)

enum {
    HMS_AVR_CLOCK_SOURCE_ASSURED = 1u,
    HMS_AVR_CLOCK_SERVICE_ASSURED = 2u,
    HMS_AVR_CLOCK_CONTINUITY_ASSURED = 4u,
    HMS_AVR_CLOCK_ALL_ASSURED = 7u
};
enum {
    HMS_AVR_CLOCK_BAD_BOOT = 1u,
    HMS_AVR_CLOCK_RESTART = 2u,
    HMS_AVR_CLOCK_CONFIG = 4u,
    HMS_AVR_CLOCK_LATE = 8u,
    HMS_AVR_CLOCK_EXHAUSTED = 16u,
    HMS_AVR_CLOCK_REGRESSION = 32u,
    HMS_AVR_CLOCK_DISCONTINUITY = 64u,
    HMS_AVR_CLOCK_BAD_GRANT = 128u
};
typedef enum {
    HMS_AVR_CLOCK_OK = 0,
    HMS_AVR_CLOCK_UNQUALIFIED = 1,
    HMS_AVR_CLOCK_FAULT = 2
} hms_avr_clock_result;

typedef struct {
    volatile uint32_t wraps, last_wraps;
    volatile uint16_t last_count;
    uint64_t boot_epoch; /* Immutable after startup init. */
    volatile uint8_t started, qualified, fault, have_last;
} hms_avr_clock;

typedef struct {
    uint64_t boot_epoch;
    uint64_t raw_tick;
    uint64_t tick_ms; /* floor(raw_tick / 250), nominal milliseconds only. */
} hms_avr_clock_sample;

/* Software initialization only. Requires Timer1 vector inactive and the
 * startup/inhibit contract above. It does not touch registers or qualify time. */
void hms_avr_clock_init(hms_avr_clock *clock, uint64_t boot_epoch);
/* One-shot setup. Requires CLKPR=0, PRTIM1 clear, TSM/PSRSYNC clear.
 * Does not reset the prescaler shared with Timer0, enable global interrupts,
 * set a pin direction, or establish electrical/supply/clock qualification. */
hms_avr_clock_result hms_avr_clock_start(hms_avr_clock *clock);
/* A TRUSTED CALLER ATTESTATION, not a measurement: source assurance covers
 * oscillator/fuses/silicon/supply/tolerance; service assurance covers the
 * strict bound since start; continuity assurance excludes unreported pauses
 * or reconfiguration. All three bits and the identical boot epoch required.
 * It never clears a fault. Neither start nor init grants qualification. */
hms_avr_clock_result hms_avr_clock_qualify(hms_avr_clock *clock,
                                        uint64_t boot_epoch, uint8_t assurances);
void hms_avr_clock_invalidate(hms_avr_clock *clock);
/* Vector helper; never manually clear TOV1 before/after calling it. */
void hms_avr_clock_overflow(hms_avr_clock *clock);
/* Output untouched unless OK. The qualified snapshot linearizes inside the
 * saved-SREG window; conversion/copy follows restoration. A later interrupt
 * may invalidate the live clock before return. Sample afresh at each effect
 * boundary and retain independent inhibition; a sample is no future grant.
 * Less than 1 nominal ms floor error, plus oscillator/initial prescaler phase
 * uncertainty; all must enter the platform's external clock-error budget.
 * No endpoint BOOT_QUALIFIED, INHIBITED or other platform flags are invented. */
hms_avr_clock_result hms_avr_clock_read(hms_avr_clock *clock,
                                     hms_avr_clock_sample *sample);

#endif
