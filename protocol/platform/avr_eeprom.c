#include "avr_eeprom.h"
#include <stddef.h>

#if defined(HMS_AVR_EEPROM_TEST)
/* Original register model is supplied by the host probe. This branch does not
 * model AVR instruction timing, electrical power loss or silicon behavior. */
extern uint8_t hms_avr_probe_control(void);
extern uint8_t hms_avr_probe_spm(void);
extern uint8_t hms_avr_probe_save_cli(void);
extern void hms_avr_probe_restore(uint8_t saved);
extern void hms_avr_probe_address(uint16_t address);
extern uint8_t hms_avr_probe_read(void);
extern void hms_avr_probe_launch_zero(void);
#define control hms_avr_probe_control
#define spm hms_avr_probe_spm
#define save_cli hms_avr_probe_save_cli
#define restore hms_avr_probe_restore
#define address_set hms_avr_probe_address
#define read_selected hms_avr_probe_read
#define launch_zero hms_avr_probe_launch_zero
#define EEPROM_BUSY 2u
#define EEPROM_INTERRUPT 8u
#define FLASH_BUSY 1u
#else
#if !defined(__AVR_ATmega328P__)
#error This register adapter is only reviewed for ATmega328P
#endif
#include <avr/io.h>
#include <avr/interrupt.h>
_Static_assert(E2END == 1023, "ATmega328P EEPROM extent");
_Static_assert(_SFR_IO_ADDR(EECR) == 0x1f, "SBI-addressable EECR");
_Static_assert(EEMPE == 2 && EEPE == 1 && EEPM1 == 5 && EEPM0 == 4,
               "Reviewed EEPROM control bits");

#define EEPROM_BUSY _BV(EEPE)
#define EEPROM_INTERRUPT _BV(EERIE)
#define FLASH_BUSY _BV(SPMEN)

static uint8_t control(void) { return EECR; }
static uint8_t spm(void) { return SPMCSR; }
static uint8_t save_cli(void) { uint8_t saved = SREG; cli(); return saved; }
static void restore(uint8_t saved) { SREG = saved; __asm__ __volatile__("" ::: "memory"); }
static void address_set(uint16_t address) { EEAR = address; }
static uint8_t read_selected(void) { EECR |= _BV(EERE); return EEDR; }

static void launch_zero(void) {
    EEDR = 0;
    /* Only an erased byte is accepted. Write-only mode: no erase operation.
     * EERIE was checked clear and no concurrent owner may change it. */
    EECR = _BV(EEPM1);
    /* SBI is two cycles on this target. Two adjacent SBI instructions keep
     * EEMPE -> EEPE within the datasheet's four-cycle window. Both operands
     * are immediate I/O bit addresses. Interrupts remain disabled here. */
    __asm__ __volatile__("sbi %0, %1\n\tsbi %0, %2"
                         : : "I" (_SFR_IO_ADDR(EECR)), "I" (EEMPE), "I" (EEPE)
                         : "memory");
}
#endif

void hms_avr_eeprom_init(hms_avr_eeprom *d, uint16_t budget) {
    if (d == NULL) return;
    d->poll_budget = budget; d->active = 0;
    d->last_status = budget == 0u ? HMS_AVR_EEPROM_BAD_CONFIG : HMS_AVR_EEPROM_OK;
}

static uint8_t begin(hms_avr_eeprom *d, uint32_t address) {
    if (d == NULL) return 0;
    if (d->active != 0u) return 0; /* Do not overwrite the outer call's status. */
    if (d->poll_budget == 0u) { d->last_status = HMS_AVR_EEPROM_BAD_CONFIG; return 0; }
    if (address >= HMS_AVR_EEPROM_BYTES) { d->last_status = HMS_AVR_EEPROM_BAD_ADDRESS; return 0; }
    d->active = 1; d->last_status = HMS_AVR_EEPROM_OK;
    return 1;
}

static uint8_t end(hms_avr_eeprom *d, uint8_t status) {
    d->last_status = status; d->active = 0;
    return status == HMS_AVR_EEPROM_OK ? 1u : 0u;
}

static uint8_t ready(uint16_t *remaining) {
    while (*remaining != 0u) {
        uint8_t c;
        *remaining = (uint16_t)(*remaining - 1u);
        c = control();
        if ((c & EEPROM_INTERRUPT) != 0u) return HMS_AVR_EEPROM_OWNER_CONFLICT;
        if ((c & EEPROM_BUSY) == 0u && (spm() & FLASH_BUSY) == 0u) return HMS_AVR_EEPROM_OK;
    }
    return HMS_AVR_EEPROM_BUSY_TIMEOUT;
}

/* Check again inside the interrupt-masked window. No waiting in this function.
 * A surprise busy/owner condition causes a refusal before touching EEAR. */
static uint8_t exclusive_ready(uint16_t *remaining) {
    uint8_t c;
    if (*remaining == 0u) return HMS_AVR_EEPROM_BUSY_TIMEOUT;
    *remaining = (uint16_t)(*remaining - 1u);
    c = control();
    if ((c & EEPROM_INTERRUPT) != 0u) return HMS_AVR_EEPROM_OWNER_CONFLICT;
    if ((c & EEPROM_BUSY) != 0u || (spm() & FLASH_BUSY) != 0u) return HMS_AVR_EEPROM_OWNER_CONFLICT;
    return HMS_AVR_EEPROM_OK;
}

static uint8_t read_at(uint16_t address, uint8_t *value, uint16_t *remaining) {
    uint8_t saved = save_cli();
    uint8_t status = exclusive_ready(remaining);
    if (status == HMS_AVR_EEPROM_OK) {
        address_set(address);
        *value = read_selected();
    }
    restore(saved);
    return status;
}

uint8_t hms_avr_eeprom_read_byte(void *user, uint32_t address, uint8_t *value) {
    hms_avr_eeprom *d = user;
    uint16_t remaining;
    uint8_t status, result;
    if (value == NULL) {
        if (d != NULL && d->active == 0u) d->last_status = HMS_AVR_EEPROM_BAD_CONFIG;
        return 0;
    }
    if (begin(d, address) == 0u) return 0;
    remaining = d->poll_budget;
    status = ready(&remaining);
    if (status == HMS_AVR_EEPROM_OK) status = read_at((uint16_t)address, &result, &remaining);
    if (status == HMS_AVR_EEPROM_OK) *value = result;
    return end(d, status);
}

uint8_t hms_avr_eeprom_program_zero_and_sync(void *user, uint32_t address) {
    hms_avr_eeprom *d = user;
    uint16_t remaining;
    uint8_t status, saved, result;
    if (begin(d, address) == 0u) return 0;
    remaining = d->poll_budget;
    status = ready(&remaining);
    if (status != HMS_AVR_EEPROM_OK) return end(d, status);
    saved = save_cli();
    status = exclusive_ready(&remaining);
    if (status == HMS_AVR_EEPROM_OK) {
        address_set((uint16_t)address);
        if (read_selected() != 0xffu) status = HMS_AVR_EEPROM_NOT_ERASED;
        else launch_zero();
    }
    restore(saved);
    if (status != HMS_AVR_EEPROM_OK) return end(d, status);
    status = ready(&remaining);
    if (status == HMS_AVR_EEPROM_OK) status = read_at((uint16_t)address, &result, &remaining);
    if (status == HMS_AVR_EEPROM_OK && result != 0u) status = HMS_AVR_EEPROM_VERIFY_FAILED;
    return end(d, status);
}
