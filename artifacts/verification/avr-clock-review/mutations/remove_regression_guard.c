#include "avr_clock.h"

/* Register shim is an original native model, not an AVR emulator. */
#if defined(HMS_AVR_CLOCK_TEST)
extern uint8_t hms_avr_clock_probe_save_cli(void);
extern void hms_avr_clock_probe_restore(uint8_t saved);
extern uint8_t hms_avr_clock_probe_read(uint8_t reg);
extern void hms_avr_clock_probe_write(uint8_t reg, uint8_t value);
#define save_cli hms_avr_clock_probe_save_cli
#define restore hms_avr_clock_probe_restore
#define READ(reg) hms_avr_clock_probe_read(reg)
#define WRITE(reg, value) hms_avr_clock_probe_write((reg), (value))
enum { R_A, R_B, R_C, R_MASK, R_FLAG, R_LOW, R_HIGH, R_POWER, R_PRESCALE, R_SYNC };
#else
#if !defined(__AVR_ATmega328P__) || !defined(F_CPU) || F_CPU != 16000000UL
#error "This clock profile requires ATmega328P and F_CPU=16000000UL"
#endif
#include <avr/io.h>
#include <avr/interrupt.h>
_Static_assert(TOV1 == 0 && TOIE1 == 0 && PRTIM1 == 3 && TSM == 7 && PSRSYNC == 0,
               "Unexpected timer bit map");
_Static_assert(_SFR_MEM_ADDR(TCNT1L) == 0x84 && _SFR_MEM_ADDR(TCNT1H) == 0x85 &&
               _SFR_MEM_ADDR(TIFR1) == 0x36 && _SFR_MEM_ADDR(TIMSK1) == 0x6f,
               "Unexpected timer register map");
static uint8_t save_cli(void) { uint8_t saved = SREG; cli(); return saved; }
static void restore(uint8_t saved) { __asm__ __volatile__("" ::: "memory"); SREG = saved; }
#define READ(reg) (reg)
#define WRITE(reg, value) ((reg) = (value))
#define R_A TCCR1A
#define R_B TCCR1B
#define R_C TCCR1C
#define R_MASK TIMSK1
#define R_FLAG TIFR1
#define R_LOW TCNT1L
#define R_HIGH TCNT1H
#define R_POWER PRR
#define R_PRESCALE CLKPR
#define R_SYNC GTCCR
#endif

static void fault(hms_avr_clock *clock, uint8_t reason) {
    clock->fault = (uint8_t)(clock->fault | reason);
    clock->qualified = 0;
}

static uint8_t source_config(void) {
    return (uint8_t)(READ(R_PRESCALE) == 0u && (READ(R_POWER) & 8u) == 0u &&
                     (READ(R_SYNC) & 0x81u) == 0u);
}

static uint8_t running_config(void) {
    return (uint8_t)(source_config() && READ(R_A) == 0u &&
                     READ(R_B) == 3u && READ(R_MASK) == 1u);
}

static uint16_t counter(void) {
    uint8_t low = READ(R_LOW); /* Latches high byte in shared TEMP. */
    uint8_t high = READ(R_HIGH);
    return (uint16_t)((uint16_t)low | ((uint16_t)high << 8));
}

void hms_avr_clock_init(hms_avr_clock *clock, uint64_t boot_epoch) {
    clock->wraps = 0; clock->last_wraps = 0; clock->last_count = 0;
    clock->boot_epoch = boot_epoch;
    clock->started = 0; clock->qualified = 0; clock->have_last = 0;
    clock->fault = (uint8_t)((boot_epoch == 0u || boot_epoch == UINT64_MAX) ?
                            HMS_AVR_CLOCK_BAD_BOOT : 0u);
}

hms_avr_clock_result hms_avr_clock_start(hms_avr_clock *clock) {
    uint8_t saved = save_cli();
    if (clock->started) fault(clock, HMS_AVR_CLOCK_RESTART);
    if (!clock->fault) {
        clock->started = 1; /* Even a failed start cannot be retried. */
        if (!source_config()) fault(clock, HMS_AVR_CLOCK_CONFIG);
        else {
            WRITE(R_MASK, 0u); WRITE(R_B, 0u); WRITE(R_A, 0u); WRITE(R_C, 0u);
            WRITE(R_HIGH, 0u); WRITE(R_LOW, 0u);
            WRITE(R_FLAG, 1u); /* W1C only TOV1; no read/modify/write. */
            WRITE(R_MASK, 1u); WRITE(R_B, 3u);
        }
    }
    hms_avr_clock_result result = clock->fault ? HMS_AVR_CLOCK_FAULT : HMS_AVR_CLOCK_UNQUALIFIED;
    restore(saved);
    return result;
}

hms_avr_clock_result hms_avr_clock_qualify(hms_avr_clock *clock,
                                        uint64_t boot_epoch, uint8_t assurances) {
    uint8_t saved = save_cli();
    if (!clock->started || boot_epoch != clock->boot_epoch || assurances != HMS_AVR_CLOCK_ALL_ASSURED)
        fault(clock, HMS_AVR_CLOCK_BAD_GRANT);
    if (!clock->fault && !running_config()) fault(clock, HMS_AVR_CLOCK_CONFIG);
    if (!clock->fault) clock->qualified = 1;
    hms_avr_clock_result result = clock->fault ? HMS_AVR_CLOCK_FAULT : HMS_AVR_CLOCK_OK;
    restore(saved);
    return result;
}

void hms_avr_clock_invalidate(hms_avr_clock *clock) {
    uint8_t saved = save_cli();
    fault(clock, HMS_AVR_CLOCK_DISCONTINUITY);
    restore(saved);
}

void hms_avr_clock_overflow(hms_avr_clock *clock) {
    uint8_t saved = save_cli();
    if (!clock->started) fault(clock, HMS_AVR_CLOCK_CONFIG);
    if (!clock->fault) {
        if (!running_config()) fault(clock, HMS_AVR_CLOCK_CONFIG);
        else if (counter() >= HMS_AVR_CLOCK_SERVICE_LIMIT || (READ(R_FLAG) & 1u) != 0u)
            fault(clock, HMS_AVR_CLOCK_LATE);
        else if (clock->wraps == UINT32_MAX) fault(clock, HMS_AVR_CLOCK_EXHAUSTED);
        else ++clock->wraps;
    }
    restore(saved);
}

hms_avr_clock_result hms_avr_clock_read(hms_avr_clock *clock,
                                     hms_avr_clock_sample *sample) {
    uint32_t high = 0;
    uint16_t low = 0;
    uint8_t saved = save_cli();
    if (clock->started && !clock->fault) {
        if (!running_config()) fault(clock, HMS_AVR_CLOCK_CONFIG);
        else {
            uint8_t before = (uint8_t)(READ(R_FLAG) & 1u);
            low = counter();
            uint8_t after = (uint8_t)(READ(R_FLAG) & 1u);
            high = clock->wraps;
            if (before && !after) fault(clock, HMS_AVR_CLOCK_CONFIG);
            else if (after) {
                if (!before) low = counter(); /* Crossed wrap during first sample. */
                if (low >= HMS_AVR_CLOCK_SERVICE_LIMIT) fault(clock, HMS_AVR_CLOCK_LATE);
                else if (high == UINT32_MAX) fault(clock, HMS_AVR_CLOCK_EXHAUSTED);
                else ++high; /* Pending compensation; flag/high word untouched. */
            }
            if (!clock->fault && clock->have_last &&
                (high < clock->last_wraps || (high == clock->last_wraps && low < clock->last_count)))
                clock->have_last = 0; /* Intentionally broken: forget regression. */
            if (!clock->fault) {
                clock->last_wraps = high; clock->last_count = low; clock->have_last = 1;
            }
        }
    }
    hms_avr_clock_result result = clock->fault ? HMS_AVR_CLOCK_FAULT :
        (clock->started && clock->qualified ? HMS_AVR_CLOCK_OK : HMS_AVR_CLOCK_UNQUALIFIED);
    restore(saved);
    if (result == HMS_AVR_CLOCK_OK) {
        uint64_t raw = ((uint64_t)high << 16) | low;
        /* high = 125*q+r, so (high*65536+low)/250 equals
         * q*32768 + floor((r*65536+low)/250). Residual <= 8191999.
         * Both divisions are 32-bit and occur after SREG restoration. */
        uint32_t quotient = high / 125u;
        uint32_t residual = ((high % 125u) << 16) | low;
        sample->boot_epoch = clock->boot_epoch;
        sample->raw_tick = raw;
        sample->tick_ms = ((uint64_t)quotient << 15) + residual / HMS_AVR_CLOCK_RAW_PER_MS;
    }
    return result;
}
