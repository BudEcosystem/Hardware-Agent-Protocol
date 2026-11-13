#include "../protocol/platform/avr_clock.h"

#if defined(HMS_AVR_CLOCK_TEST)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { R_A, R_B, R_C, R_MASK, R_FLAG, R_LOW, R_HIGH, R_POWER, R_PRESCALE, R_SYNC };
static unsigned long checks;
static unsigned cases, rollover_cases, low_cases, sreg_cases, random_cases;
#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "check failed line %u: %s\n", (unsigned)__LINE__, #x); exit(1); } } while (0)
static hms_avr_clock clock_state;
static hms_avr_clock_sample sample;
static uint8_t regs[10], sreg, temp, saved_stack[4];
static uint16_t hw_counter;
static uint64_t actual_raw;
static unsigned depth, saves, restores, accesses, writes, low_reads, high_reads, flag_reads;
static unsigned irq_low_reads, irq_high_reads, irq_flag_reads;
static unsigned inject_at, inject_after, inject_second, save_irq, restore_irq, restore_invalidate;
static uint8_t write_log[20], value_log[20];
static unsigned write_count;

static void advance(uint32_t count) {
    uint64_t next = actual_raw + count;
    if ((next >> 16) != (actual_raw >> 16)) regs[R_FLAG] |= 1u;
    actual_raw = next; hw_counter = (uint16_t)next;
}

static void irq(void) {
    uint8_t saved = sreg;
    unsigned low_before = low_reads, high_before = high_reads, flag_before = flag_reads;
    CHECK(depth == 0u && (sreg & 0x80u) && (regs[R_MASK] & 1u) && (regs[R_FLAG] & 1u));
    sreg = (uint8_t)(sreg & 0x7fu);
    regs[R_FLAG] &= 0xfeu; /* Hardware vector entry, not a driver write. */
    hms_avr_clock_overflow(&clock_state);
    irq_low_reads += low_reads - low_before; irq_high_reads += high_reads - high_before;
    irq_flag_reads += flag_reads - flag_before;
    CHECK(depth == 0u && (sreg & 0x80u) == 0u);
    sreg = saved; /* Saved ISR state and RETI, no cycle model. */
}

uint8_t hms_avr_clock_probe_save_cli(void) {
    uint8_t saved = sreg;
    if (save_irq) { save_irq = 0; advance(1); irq(); }
    CHECK(depth < sizeof(saved_stack)); saved_stack[depth++] = saved;
    ++saves; sreg = (uint8_t)(sreg & 0x7fu);
    return saved;
}

void hms_avr_clock_probe_restore(uint8_t saved) {
    CHECK(depth != 0u && saved_stack[depth - 1u] == saved);
    --depth; ++restores; sreg = saved;
    if (restore_irq) { restore_irq = 0; advance(1); irq(); }
    if (restore_invalidate) { restore_invalidate = 0; hms_avr_clock_invalidate(&clock_state); }
}

static void hook(unsigned after) {
    if (inject_at == accesses && inject_after == after) {
        inject_at = inject_second; inject_second = 0; advance(1);
    }
}

uint8_t hms_avr_clock_probe_read(uint8_t reg) {
    uint8_t result;
    CHECK(depth == 1u && (sreg & 0x80u) == 0u && reg < sizeof(regs));
    ++accesses; hook(0);
    if (reg == R_LOW) { ++low_reads; result = (uint8_t)hw_counter; temp = (uint8_t)(hw_counter >> 8); }
    else if (reg == R_HIGH) { ++high_reads; result = temp; }
    else { if (reg == R_FLAG) ++flag_reads; result = regs[reg]; }
    hook(1); return result;
}

void hms_avr_clock_probe_write(uint8_t reg, uint8_t value) {
    CHECK(depth == 1u && (sreg & 0x80u) == 0u && reg < sizeof(regs));
    CHECK(write_count < sizeof(write_log));
    write_log[write_count] = reg; value_log[write_count++] = value; ++writes;
    if (reg == R_HIGH) temp = value;
    else if (reg == R_LOW) { hw_counter = (uint16_t)(((uint16_t)temp << 8) | value); actual_raw = hw_counter; }
    else if (reg == R_FLAG) regs[reg] = (uint8_t)(regs[reg] & (uint8_t)~value);
    else regs[reg] = value;
}

static void reset(void) {
    CHECK(depth == 0u && saves == restores);
    memset(regs, 0, sizeof(regs)); memset(&sample, 0xa5, sizeof(sample));
    sreg = 0x80u; temp = 0; hw_counter = 0; actual_raw = 0;
    accesses = writes = low_reads = high_reads = flag_reads = write_count = 0;
    irq_low_reads = irq_high_reads = irq_flag_reads = 0;
    inject_at = inject_after = inject_second = save_irq = restore_irq = restore_invalidate = 0;
    hms_avr_clock_init(&clock_state, UINT64_C(0x0102030405060708));
}

static void start(void) {
    CHECK(hms_avr_clock_start(&clock_state) == HMS_AVR_CLOCK_UNQUALIFIED);
    CHECK(!clock_state.qualified && !clock_state.fault && clock_state.started);
}

static void qualify(void) {
    CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch,
                              HMS_AVR_CLOCK_ALL_ASSURED) == HMS_AVR_CLOCK_OK);
}

static void ready(void) { reset(); start(); qualify(); accesses = 0; }

static hms_avr_clock_result read_sample(void) {
    unsigned old_writes = writes, old_low = low_reads, old_high = high_reads, old_flag = flag_reads;
    unsigned old_irq_low = irq_low_reads, old_irq_high = irq_high_reads, old_irq_flag = irq_flag_reads;
    uint8_t old_sreg = sreg;
    hms_avr_clock_sample prior = sample;
    hms_avr_clock_result result = hms_avr_clock_read(&clock_state, &sample);
    CHECK(writes == old_writes && sreg == old_sreg && saves == restores && depth == 0u);
    unsigned own_low = low_reads - old_low - (irq_low_reads - old_irq_low);
    unsigned own_high = high_reads - old_high - (irq_high_reads - old_irq_high);
    unsigned own_flag = flag_reads - old_flag - (irq_flag_reads - old_irq_flag);
    CHECK(own_low <= 2u && own_high == own_low && own_flag <= 2u);
    if (result != HMS_AVR_CLOCK_OK) CHECK(memcmp(&prior, &sample, sizeof(sample)) == 0);
    else {
        CHECK(sample.boot_epoch == clock_state.boot_epoch && sample.raw_tick <= HMS_AVR_CLOCK_RAW_MAX);
        CHECK(sample.tick_ms == sample.raw_tick / 250u && sample.tick_ms != UINT64_MAX);
    }
    return result;
}

static void lifecycle(void) {
    static const uint8_t expected_reg[] = {R_MASK,R_B,R_A,R_C,R_HIGH,R_LOW,R_FLAG,R_MASK,R_B};
    static const uint8_t expected_value[] = {0,0,0,0,0,0,1,1,3};
    reset(); CHECK(read_sample() == HMS_AVR_CLOCK_UNQUALIFIED);
    regs[R_FLAG] = 0x27u; start();
    CHECK(write_count == sizeof(expected_reg));
    CHECK(memcmp(write_log, expected_reg, sizeof(expected_reg)) == 0);
    CHECK(memcmp(value_log, expected_value, sizeof(expected_value)) == 0);
    CHECK(regs[R_FLAG] == 0x26u && regs[R_SYNC] == 0u && regs[R_PRESCALE] == 0u);
    CHECK(read_sample() == HMS_AVR_CLOCK_UNQUALIFIED); qualify();
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 0u);
    advance(999); CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.tick_ms == 3u);
    unsigned previous_writes = writes;
    CHECK(hms_avr_clock_start(&clock_state) == HMS_AVR_CLOCK_FAULT && writes == previous_writes);
    CHECK(clock_state.fault == HMS_AVR_CLOCK_RESTART && hw_counter == 999u);
    CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch, 7u) == HMS_AVR_CLOCK_FAULT);
    CHECK(read_sample() == HMS_AVR_CLOCK_FAULT);
    ready(); hms_avr_clock_invalidate(&clock_state); CHECK(read_sample() == HMS_AVR_CLOCK_FAULT);
    CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch, 7u) == HMS_AVR_CLOCK_FAULT);
    CHECK(clock_state.fault == HMS_AVR_CLOCK_DISCONTINUITY);
    for (unsigned i = 0; i < 2u; ++i) {
        reset(); hms_avr_clock_init(&clock_state, i == 0u ? 0u : UINT64_MAX);
        CHECK(hms_avr_clock_start(&clock_state) == HMS_AVR_CLOCK_FAULT && writes == 0u);
        CHECK(clock_state.fault == HMS_AVR_CLOCK_BAD_BOOT);
    }
    reset(); hms_avr_clock_init(&clock_state, UINT64_MAX - 1u); start(); qualify();
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.boot_epoch == UINT64_MAX - 1u);
    ++cases;
}

static void grants(void) {
    for (unsigned a = 0; a < 256u; ++a) {
        reset(); start();
        CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch, (uint8_t)a) ==
              (a == 7u ? HMS_AVR_CLOCK_OK : HMS_AVR_CLOCK_FAULT));
        CHECK((clock_state.fault == 0u) == (a == 7u));
    }
    reset(); CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch, 7u) == HMS_AVR_CLOCK_FAULT);
    reset(); start(); CHECK(hms_avr_clock_qualify(&clock_state, clock_state.boot_epoch + 1u, 7u) == HMS_AVR_CLOCK_FAULT);
    CHECK(clock_state.fault == HMS_AVR_CLOCK_BAD_GRANT); ++cases;
}

static void all_saved_status(void) {
    for (unsigned i = 0; i < 256u; ++i) {
        reset(); sreg = (uint8_t)i; start(); CHECK(sreg == i); qualify(); CHECK(sreg == i);
        CHECK(read_sample() == HMS_AVR_CLOCK_OK && sreg == i);
        /* Direct unit call checks save/restore for all patterns. Real vector entry has I=0. */
        hms_avr_clock_overflow(&clock_state); CHECK(sreg == i && clock_state.wraps == 1u);
        hms_avr_clock_invalidate(&clock_state); CHECK(sreg == i);
        CHECK(read_sample() == HMS_AVR_CLOCK_FAULT && sreg == i); ++sreg_cases;
    }
    ++cases;
}

static void every_low_value(void) {
    for (unsigned pending = 0; pending < 2u; ++pending) {
        for (uint32_t low = 0; low <= UINT16_MAX; ++low) {
            ready(); clock_state.wraps = 7u;
            actual_raw = (UINT64_C(7) + pending) * 65536u + low;
            hw_counter = (uint16_t)low; regs[R_FLAG] = (uint8_t)pending;
            hms_avr_clock_result result = read_sample();
            if (pending && low >= HMS_AVR_CLOCK_SERVICE_LIMIT)
                CHECK(result == HMS_AVR_CLOCK_FAULT && clock_state.fault == HMS_AVR_CLOCK_LATE);
            else CHECK(result == HMS_AVR_CLOCK_OK && sample.raw_tick == actual_raw);
            CHECK(clock_state.wraps == 7u && (regs[R_FLAG] & 1u) == pending); ++low_cases;
        }
    }
    ++cases;
}

static void rollover_boundaries(void) {
    /* Every before/after register-read boundary of the initial read, including
     * low/high TEMP latching. Transition reread boundaries are covered below. */
    for (unsigned after = 0; after < 2u; ++after) {
        for (unsigned position = 1; position <= 10u; ++position) {
            ready(); advance(65535u); accesses = 0;
            inject_at = position; inject_after = after;
            CHECK(read_sample() == HMS_AVR_CLOCK_OK && inject_at == 0u);
            CHECK(sample.raw_tick == (after && position == 10u ? 65535u : 65536u));
            CHECK(clock_state.wraps == 0u && (regs[R_FLAG] & 1u));
            irq(); CHECK(clock_state.wraps == 1u && read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 65536u);
            ++rollover_cases;
        }
    }
    /* All read boundaries with a preexisting pending overflow. */
    for (unsigned after = 0; after < 2u; ++after) {
        for (unsigned position = 1; position <= 10u; ++position) {
            ready(); advance(65536u); accesses = 0; inject_at = position; inject_after = after;
            CHECK(read_sample() == HMS_AVR_CLOCK_OK && inject_at == 0u);
            CHECK(sample.raw_tick == (position < 8u || (position == 8u && !after) ? 65537u : 65536u));
            ++rollover_cases;
        }
    }
    for (unsigned after = 0; after < 2u; ++after) {
        for (unsigned position = 11; position <= 12u; ++position) {
            ready(); advance(65535u); accesses = 0;
            inject_at = 8; inject_second = position; inject_after = after;
            CHECK(read_sample() == HMS_AVR_CLOCK_OK && !inject_at && !inject_second);
            CHECK(sample.raw_tick == (position == 11u && !after ? 65537u : 65536u));
            CHECK(actual_raw == 65537u && low_reads == 2u && high_reads == 2u);
            ++rollover_cases;
        }
    }
    ready(); advance(65535u); save_irq = 1;
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 65536u && clock_state.wraps == 1u);
    ready(); advance(65535u); restore_irq = 1;
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 65535u && clock_state.wraps == 1u);
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 65536u);
    ready(); restore_invalidate = 1;
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && clock_state.fault == HMS_AVR_CLOCK_DISCONTINUITY);
    CHECK(read_sample() == HMS_AVR_CLOCK_FAULT); rollover_cases += 3u; ++cases;
}

static void late_and_alias(void) {
    ready(); advance(65536u + 32767u); CHECK(read_sample() == HMS_AVR_CLOCK_OK);
    irq(); CHECK(clock_state.wraps == 1u && !clock_state.fault);
    ready(); advance(65536u + 32768u); irq(); CHECK(clock_state.fault == HMS_AVR_CLOCK_LATE);
    ready(); advance(65536u); hms_avr_clock_overflow(&clock_state);
    CHECK(clock_state.fault == HMS_AVR_CLOCK_LATE); /* Helper without vector clearing is invalid. */
    ready(); advance(2u * 65536u + 17u);
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == 65536u + 17u);
    CHECK(sample.raw_tick + 65536u == actual_raw); /* Deliberate contract violation aliases. */
    irq(); CHECK(clock_state.wraps == 1u && !clock_state.fault);
    hms_avr_clock_invalidate(&clock_state); CHECK(read_sample() == HMS_AVR_CLOCK_FAULT);
    ++cases;
}

static void config_faults(void) {
    const uint8_t registers[] = {R_A,R_B,R_MASK,R_POWER,R_PRESCALE,R_SYNC,R_SYNC};
    const uint8_t bits[] = {1,4,2,8,1,1,128};
    for (unsigned i = 0; i < sizeof(registers); ++i) {
        ready(); regs[registers[i]] ^= bits[i]; CHECK(read_sample() == HMS_AVR_CLOCK_FAULT);
        CHECK(clock_state.fault == HMS_AVR_CLOCK_CONFIG);
        regs[registers[i]] ^= bits[i]; CHECK(read_sample() == HMS_AVR_CLOCK_FAULT);
        ready(); regs[registers[i]] ^= bits[i]; advance(65536u); irq();
        CHECK(clock_state.fault == HMS_AVR_CLOCK_CONFIG);
        reset(); if (i >= 3u) {
            regs[registers[i]] ^= bits[i]; CHECK(hms_avr_clock_start(&clock_state) == HMS_AVR_CLOCK_FAULT);
            CHECK(writes == 0u && clock_state.started);
        }
    }
    reset(); hms_avr_clock_overflow(&clock_state); CHECK(clock_state.fault == HMS_AVR_CLOCK_CONFIG);
    ++cases;
}

static void exhaustion_and_regression(void) {
    ready(); clock_state.wraps = UINT32_MAX; hw_counter = UINT16_MAX;
    actual_raw = HMS_AVR_CLOCK_RAW_MAX;
    CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == HMS_AVR_CLOCK_RAW_MAX);
    advance(1); CHECK(read_sample() == HMS_AVR_CLOCK_FAULT && clock_state.fault == HMS_AVR_CLOCK_EXHAUSTED);
    ready(); clock_state.wraps = UINT32_MAX; advance(65536u); irq();
    CHECK(clock_state.fault == HMS_AVR_CLOCK_EXHAUSTED && clock_state.wraps == UINT32_MAX);
    ready(); advance(100); CHECK(read_sample() == HMS_AVR_CLOCK_OK);
    --hw_counter; CHECK(read_sample() == HMS_AVR_CLOCK_FAULT && clock_state.fault == HMS_AVR_CLOCK_REGRESSION);
    ready(); advance(65536u); irq(); CHECK(read_sample() == HMS_AVR_CLOCK_OK);
    clock_state.wraps = 0; CHECK(read_sample() == HMS_AVR_CLOCK_FAULT && clock_state.fault == HMS_AVR_CLOCK_REGRESSION);
    ++cases;
}

static void conversion_edges(void) {
    const uint32_t high_values[] = {0,1,124,125,126,65535,65536,0x7fffffffu,0x80000000u,UINT32_MAX};
    const uint16_t low_values[] = {0,1,124,125,249,250,251,32767,32768,65535};
    for (unsigned h = 0; h < sizeof(high_values)/sizeof(high_values[0]); ++h) {
        for (unsigned l = 0; l < sizeof(low_values)/sizeof(low_values[0]); ++l) {
            ready(); clock_state.wraps = high_values[h]; hw_counter = low_values[l];
            actual_raw = ((uint64_t)high_values[h] << 16) | low_values[l];
            CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == actual_raw && sample.tick_ms == actual_raw / 250u);
        }
    }
    ++cases;
}

static void bounded_sequence(void) {
    uint32_t rng = 0x29b741c3u;
    ready();
    for (unsigned i = 0; i < 50000u; ++i) {
        rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
        advance(rng % 1000u); /* At most 999 ticks until service, below bound. */
        CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == actual_raw);
        if (regs[R_FLAG] & 1u) irq();
        CHECK(read_sample() == HMS_AVR_CLOCK_OK && sample.raw_tick == actual_raw);
        ++random_cases;
    }
    ++cases;
}

int main(void) {
    lifecycle(); grants(); all_saved_status(); every_low_value(); rollover_boundaries();
    late_and_alias(); config_faults(); exhaustion_and_regression(); conversion_edges(); bounded_sequence();
    CHECK(depth == 0u && saves == restores);
    printf("{\"cases\":%u,\"assertions\":%lu,\"low_counter_cases\":%u,\"rollover_cases\":%u,"
           "\"sreg_patterns\":%u,\"bounded_sequence_cases\":%u,\"alias_counterexamples\":1,"
           "\"target_executed\":false}\n", cases, checks, low_cases, rollover_cases, sreg_cases, random_cases);
    return 0;
}
#else
/* Original, separately linked inspection image. Never uploaded or executed. */
#include <avr/interrupt.h>
hms_avr_clock hms_avr_clock_probe_state;
hms_avr_clock_sample hms_avr_clock_probe_sample;
volatile uint8_t hms_avr_clock_probe_result;
ISR(TIMER1_OVF_vect) { hms_avr_clock_overflow(&hms_avr_clock_probe_state); }
int main(void) {
    hms_avr_clock_init(&hms_avr_clock_probe_state, UINT64_C(1));
    hms_avr_clock_probe_result = (uint8_t)hms_avr_clock_start(&hms_avr_clock_probe_state);
    /* Zero assurances deliberately cannot qualify a real installation. */
    hms_avr_clock_probe_result = (uint8_t)hms_avr_clock_qualify(&hms_avr_clock_probe_state, 1u, 0u);
    hms_avr_clock_probe_result = (uint8_t)hms_avr_clock_read(&hms_avr_clock_probe_state, &hms_avr_clock_probe_sample);
    hms_avr_clock_invalidate(&hms_avr_clock_probe_state);
    return 0;
}
#endif
