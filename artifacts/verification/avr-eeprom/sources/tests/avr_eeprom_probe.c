/* Original register-model tests; AVR branch is cross-linked ONLY, never run.
 * No model result establishes electrical, interrupt-latency or silicon timing.
 */
#include "../protocol/platform/avr_eeprom.h"
#include "../protocol/platform/boot_epoch.h"
#include <stddef.h>
#include <stdint.h>

typedef struct {
    hms_avr_eeprom driver;
    uint8_t incarnation[16];
} platform_context;

static uint8_t bank_read(void *user, uint32_t address, uint8_t *value) {
    platform_context *p = user;
    return hms_avr_eeprom_read_byte(&p->driver, address, value);
}
static uint8_t bank_program(void *user, uint32_t address) {
    platform_context *p = user;
    return hms_avr_eeprom_program_zero_and_sync(&p->driver, address);
}
static uint8_t incarnation(void *user, uint8_t index) {
    platform_context *p = user;
    return p->incarnation[index];
}

#if defined(__AVR__)
/* Reachable hardware register callbacks in a linked inspection artifact.
 * DO NOT UPLOAD OR EXECUTE: no supply/BOD/EEPROM qualification is installed.
 * It never sets any endpoint/platform qualification flag. */
static platform_context context;
static hms_boot_reservation reservation;
volatile uint8_t hms_avr_probe_status;
volatile uint64_t hms_avr_probe_epoch;
uint8_t hms_avr_eeprom_abi_size[sizeof(hms_avr_eeprom)];

int main(void) {
    hms_boot_storage storage;
    uint8_t i;
    for (i = 0; i < 16u; ++i) context.incarnation[i] = (uint8_t)(i + 1u);
    hms_avr_eeprom_init(&context.driver, 60000u);
    storage.user = &context; storage.read_byte = bank_read;
    storage.program_zero_and_sync = bank_program; storage.incarnation_byte = incarnation;
    storage.region_base = 0; storage.capacity = 992u;
    hms_boot_init(&reservation);
    hms_avr_probe_status = hms_boot_acquire(&reservation, &storage);
    hms_avr_probe_epoch = hms_boot_reserved_epoch(&reservation);
    for (;;) { }
}
#else
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long assertions;
static unsigned cases;
#define CHECK(x) do { ++assertions; if (!(x)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static struct {
    uint8_t bytes[HMS_AVR_EEPROM_BYTES];
    uint16_t selected;
    uint8_t sreg, saved, pending, final_byte, stuck, interrupt_enable;
    unsigned checks, spm_checks, addresses, reads, launches, enters, exits;
    unsigned ee_busy, spm_busy, completion_busy, inject_check;
    uint8_t inject_bits, inject_spm;
    hms_avr_eeprom *reenter;
    uint8_t reentered;
} m;

static void reset_model(uint8_t irq) {
    memset(&m, 0, sizeof(m)); memset(m.bytes, 0xff, sizeof(m.bytes));
    m.sreg = irq; m.final_byte = 0;
}

uint8_t hms_avr_probe_control(void) {
    uint8_t bits = m.interrupt_enable;
    ++m.checks;
    if (m.reenter != NULL && m.reentered == 0u) {
        uint8_t old = 0xab;
        m.reentered = 1;
        CHECK(hms_avr_eeprom_read_byte(m.reenter, 0, &old) == 0u);
        CHECK(hms_avr_eeprom_program_zero_and_sync(m.reenter, 0) == 0u);
        CHECK(old == 0xabu);
    }
    if (m.inject_check == m.checks) bits |= m.inject_bits;
    if (m.ee_busy != 0u) { --m.ee_busy; bits |= 2u; }
    if (m.pending != 0u) {
        if (m.stuck != 0u || m.completion_busy != 0u) {
            bits |= 2u;
            if (m.completion_busy != 0u) --m.completion_busy;
        } else {
            m.bytes[m.selected] = m.final_byte; m.pending = 0;
        }
    }
    return bits;
}
uint8_t hms_avr_probe_spm(void) {
    ++m.spm_checks;
    if (m.inject_check == m.checks && m.inject_spm != 0u) return 1;
    if (m.spm_busy != 0u) { --m.spm_busy; return 1; }
    return 0;
}
uint8_t hms_avr_probe_save_cli(void) {
    CHECK(m.enters == m.exits); ++m.enters;
    m.saved = m.sreg; m.sreg &= 0x7fu; return m.saved;
}
void hms_avr_probe_restore(uint8_t saved) {
    CHECK(m.enters == m.exits + 1u); CHECK(saved == m.saved);
    m.sreg = saved; ++m.exits;
}
void hms_avr_probe_address(uint16_t address) {
    CHECK(address < HMS_AVR_EEPROM_BYTES); CHECK((m.sreg & 0x80u) == 0u);
    CHECK(m.enters == m.exits + 1u); m.selected = address; ++m.addresses;
}
uint8_t hms_avr_probe_read(void) {
    CHECK((m.sreg & 0x80u) == 0u); CHECK(m.enters == m.exits + 1u);
    CHECK(m.pending == 0u); ++m.reads; return m.bytes[m.selected];
}
void hms_avr_probe_launch_zero(void) {
    CHECK((m.sreg & 0x80u) == 0u); CHECK(m.enters == m.exits + 1u);
    CHECK(m.pending == 0u); CHECK(m.bytes[m.selected] == 0xffu);
    ++m.launches; m.pending = 1;
}

static void balanced(uint8_t irq, const hms_avr_eeprom *d) {
    CHECK(m.enters == m.exits); CHECK(m.sreg == irq); CHECK(d->active == 0u);
    CHECK(m.checks <= d->poll_budget);
}

static void invalid_inputs(void) {
    hms_avr_eeprom d; uint8_t value = 0xab;
    const uint32_t invalid[] = {1024u, 65535u, UINT32_MAX};
    size_t i;
    ++cases; reset_model(0x80); hms_avr_eeprom_init(&d, 0);
    CHECK(hms_avr_eeprom_read_byte(&d, 0, &value) == 0u);
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 0) == 0u);
    hms_avr_eeprom_init(&d, 8);
    for (i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        CHECK(hms_avr_eeprom_read_byte(&d, invalid[i], &value) == 0u);
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d, invalid[i]) == 0u);
        CHECK(d.last_status == HMS_AVR_EEPROM_BAD_ADDRESS);
    }
    CHECK(hms_avr_eeprom_read_byte(NULL, 0, &value) == 0u);
    CHECK(hms_avr_eeprom_program_zero_and_sync(NULL, 0) == 0u);
    CHECK(hms_avr_eeprom_read_byte(&d, 0, NULL) == 0u);
    CHECK(value == 0xabu); CHECK(m.checks == 0u && m.addresses == 0u && m.launches == 0u);
    balanced(0x80, &d);
}

static void every_address(void) {
    hms_avr_eeprom d; uint16_t a; uint8_t value;
    ++cases;
    for (a = 0; a < HMS_AVR_EEPROM_BYTES; ++a) {
        uint8_t irq = (a & 1u) != 0u ? 0x80u : 0u;
        reset_model(irq); hms_avr_eeprom_init(&d, 2); m.bytes[a] = (uint8_t)(a ^ 0x5au);
        CHECK(hms_avr_eeprom_read_byte(&d, a, &value) == 1u);
        CHECK(value == (uint8_t)(a ^ 0x5au)); CHECK(m.selected == a && m.checks == 2u);
        CHECK(m.launches == 0u); balanced(irq, &d);
    }
}

static void write_edges(void) {
    hms_avr_eeprom d; unsigned i, a;
    ++cases;
    for (a = 0; a <= 1023u; a += 1023u) {
        uint8_t irq = a == 0u ? 0x80u : 0u;
        reset_model(irq); hms_avr_eeprom_init(&d, 7); m.completion_busy = 3;
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d, a) == 1u);
        CHECK(m.launches == 1u && m.checks == 7u && m.reads == 2u);
        for (i = 0; i < sizeof(m.bytes); ++i) CHECK(m.bytes[i] == (i == a ? 0u : 0xffu));
        balanced(irq, &d);
    }
}

static void never_rewrite(void) {
    hms_avr_eeprom d; unsigned value;
    ++cases;
    for (value = 0; value < 255u; ++value) {
        reset_model(0x80); hms_avr_eeprom_init(&d, 8); m.bytes[100] = (uint8_t)value;
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 100) == 0u);
        CHECK(d.last_status == HMS_AVR_EEPROM_NOT_ERASED && m.launches == 0u);
        CHECK(m.bytes[100] == value); balanced(0x80, &d);
    }
}

static void busy_and_clear(void) {
    hms_avr_eeprom d; uint8_t value = 0xaa; unsigned kind;
    ++cases;
    for (kind = 0; kind < 2u; ++kind) {
        reset_model(0x80); hms_avr_eeprom_init(&d, 7); value = 0xaa;
        if (kind == 0u) m.ee_busy = 20; else m.spm_busy = 20;
        CHECK(hms_avr_eeprom_read_byte(&d, 0, &value) == 0u);
        CHECK(d.last_status == HMS_AVR_EEPROM_BUSY_TIMEOUT);
        CHECK(m.checks == 7u && m.addresses == 0u && m.enters == 0u && value == 0xaau);
        balanced(0x80, &d);
        reset_model(0); hms_avr_eeprom_init(&d, 4);
        if (kind == 0u) m.ee_busy = 2; else m.spm_busy = 2;
        CHECK(hms_avr_eeprom_read_byte(&d, 0, &value) == 1u);
        CHECK(m.checks == 4u && value == 0xffu); balanced(0, &d);
    }
}

static void critical_races(void) {
    hms_avr_eeprom d; uint8_t value; unsigned kind, write;
    ++cases;
    for (kind = 0; kind < 3u; ++kind) for (write = 0; write < 2u; ++write) {
        reset_model(0x80); hms_avr_eeprom_init(&d, 8); value = 0x5a;
        m.inject_check = 2; m.inject_bits = kind == 0u ? 2u : kind == 1u ? 8u : 0u;
        m.inject_spm = kind == 2u ? 1u : 0u;
        CHECK((write != 0u ? hms_avr_eeprom_program_zero_and_sync(&d, 0) :
               hms_avr_eeprom_read_byte(&d, 0, &value)) == 0u);
        CHECK(d.last_status == HMS_AVR_EEPROM_OWNER_CONFLICT);
        CHECK(m.addresses == 0u && m.launches == 0u && value == 0x5au); balanced(0x80, &d);
    }
}

static void exhausted_budget(void) {
    hms_avr_eeprom d; unsigned budget;
    ++cases;
    for (budget = 1; budget <= 4u; ++budget) {
        reset_model(0x80); hms_avr_eeprom_init(&d, (uint16_t)budget);
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 0) == (budget == 4u ? 1u : 0u));
        CHECK(m.checks == budget); CHECK(m.launches == (budget >= 2u ? 1u : 0u));
        if (budget == 3u) CHECK(m.bytes[0] == 0u); /* failure after completed write */
        balanced(0x80, &d);
    }
}

static void postlaunch_timeout(void) {
    hms_avr_eeprom d;
    ++cases; reset_model(0); hms_avr_eeprom_init(&d, 5); m.stuck = 1;
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 700) == 0u);
    CHECK(d.last_status == HMS_AVR_EEPROM_BUSY_TIMEOUT);
    CHECK(m.pending == 1u && m.launches == 1u && m.checks == 5u); balanced(0, &d);
}

static void verify_and_final_race(void) {
    hms_avr_eeprom d; unsigned kind;
    ++cases;
    for (kind = 0; kind < 2u; ++kind) {
        reset_model(0x80); hms_avr_eeprom_init(&d, 8);
        if (kind == 0u) m.final_byte = 0x7f;
        else { m.inject_check = 4; m.inject_bits = 8; }
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 1) == 0u);
        CHECK(d.last_status == (kind == 0u ? HMS_AVR_EEPROM_VERIFY_FAILED : HMS_AVR_EEPROM_OWNER_CONFLICT));
        CHECK(m.launches == 1u); balanced(0x80, &d);
    }
}

static void owner_and_reentry(void) {
    hms_avr_eeprom d; uint8_t value;
    ++cases; reset_model(0x80); hms_avr_eeprom_init(&d, 8); m.interrupt_enable = 8;
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d, 0) == 0u);
    CHECK(d.last_status == HMS_AVR_EEPROM_OWNER_CONFLICT);
    CHECK(m.addresses == 0u && m.launches == 0u); balanced(0x80, &d);
    reset_model(0x80); hms_avr_eeprom_init(&d, 8); m.reenter = &d;
    CHECK(hms_avr_eeprom_read_byte(&d, 0, &value) == 1u);
    CHECK(m.reentered == 1u && value == 0xffu && d.last_status == HMS_AVR_EEPROM_OK);
    CHECK(m.launches == 0u); balanced(0x80, &d);
}

static hms_boot_storage setup_bank(platform_context *p) {
    hms_boot_storage storage; unsigned i;
    hms_avr_eeprom_init(&p->driver, 8);
    for (i = 0; i < 16u; ++i) p->incarnation[i] = (uint8_t)(i + 1u);
    storage.user = p; storage.read_byte = bank_read; storage.program_zero_and_sync = bank_program;
    storage.incarnation_byte = incarnation; storage.region_base = 0; storage.capacity = 3;
    for (i = 0; i < HMS_BOOT_HEADER_BYTES; ++i) m.bytes[i] = hms_boot_header_byte(&storage, (uint8_t)i);
    return storage;
}

static void bank_torn_and_latch(void) {
    platform_context p; hms_boot_storage s; hms_boot_reservation r; unsigned launches;
    ++cases; reset_model(0x80); s = setup_bank(&p); m.final_byte = 0x7f;
    hms_boot_init(&r); CHECK(hms_boot_acquire(&r, &s) == HMS_BOOT_STORAGE_ERROR);
    CHECK(hms_boot_reserved_epoch(&r) == 0u && m.bytes[32] == 0x7fu);
    launches = m.launches; m.final_byte = 0;
    CHECK(hms_boot_acquire(&r, &s) == HMS_BOOT_STORAGE_ERROR && m.launches == launches);
    hms_boot_init(&r); CHECK(hms_boot_acquire(&r, &s) == HMS_BOOT_RESERVED);
    CHECK(hms_boot_reserved_epoch(&r) == 2u && m.bytes[33] == 0u && m.launches == launches + 1u);
    CHECK(m.sreg == 0x80u && m.enters == m.exits);
}

static void bank_exhaustion(void) {
    platform_context p; hms_boot_storage s; hms_boot_reservation r; unsigned n;
    ++cases; reset_model(0); s = setup_bank(&p);
    for (n = 1; n <= 3u; ++n) {
        hms_boot_init(&r); CHECK(hms_boot_acquire(&r, &s) == HMS_BOOT_RESERVED);
        CHECK(hms_boot_reserved_epoch(&r) == n);
    }
    hms_boot_init(&r); CHECK(hms_boot_acquire(&r, &s) == HMS_BOOT_EXHAUSTED);
    CHECK(hms_boot_reserved_epoch(&r) == 0u && m.launches == 3u);
    CHECK(m.sreg == 0u && m.enters == m.exits);
}

int main(void) {
    invalid_inputs(); every_address(); write_edges(); never_rewrite(); busy_and_clear();
    critical_races(); exhausted_budget(); postlaunch_timeout(); verify_and_final_race();
    owner_and_reentry(); bank_torn_and_latch(); bank_exhaustion();
    printf("{\"cases\":%u,\"assertions\":%lu,\"modeled_addresses\":1024,"
           "\"non_erased_values_refused\":255,\"target_executed\":false}\n", cases, assertions);
    return 0;
}
#endif
