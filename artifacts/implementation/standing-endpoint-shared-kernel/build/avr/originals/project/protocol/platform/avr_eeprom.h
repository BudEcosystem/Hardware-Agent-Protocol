#ifndef HMS_AVR_EEPROM_H
#define HMS_AVR_EEPROM_H

#include <stdint.h>

#define HMS_AVR_EEPROM_BYTES 1024u

enum hms_avr_eeprom_status {
    HMS_AVR_EEPROM_OK, HMS_AVR_EEPROM_BAD_CONFIG, HMS_AVR_EEPROM_BAD_ADDRESS,
    HMS_AVR_EEPROM_BUSY_TIMEOUT,
    HMS_AVR_EEPROM_OWNER_CONFLICT, HMS_AVR_EEPROM_NOT_ERASED,
    HMS_AVR_EEPROM_VERIFY_FAILED
};

/* Original ATmega328P register adapter, NOT electrical qualification.
 *
 * One startup owner, no other EEPROM access (including ISR/debugger/programmer)
 * and no overlapping self-programming. EERIE must remain disabled. Configuration
 * and this object remain valid and immutable except this module's state.
 *
 * poll_budget bounds readiness checks across one whole callback (including
 * the masked rechecks); each checks EECR and, if not busy, SPMCSR.
 * it is not microseconds and supplies no wall-clock deadline. No watchdog is
 * fed. Interrupt state is saved/restored around short access/launch windows;
 * busy waiting occurs outside them. If interrupts were disabled on entry they
 * remain disabled: the caller owns its timer/service consequences. Reentry
 * returns0 without altering the active outer callback's diagnostic status.
 * This adapter owns EEPM mode selection and leaves it at write-only after a
 * launch; it does not restore a previous mode or enable EEPROM interrupts.
 *
 * Returns1 only after completion and, for programming, zero readback. Returns0
 * may follow a launched or completed write; never retry as an uncommitted
 * mutation. The finite bank treats any resulting non-FF byte as consumed.
 *
 * Use with hms_boot_storage only after board-specific power/reset/BOD, voltage
 * and clock envelope, retention, target-byte fault containment, immutable
 * header/incarnation, erase/update continuity and exclusive ownership have been
 * qualified. EEPE clear plus readback does not prove those assumptions. This
 * module never asserts BOOT_QUALIFIED, formats, erases, or increments an epoch.
 */
typedef struct {
    uint16_t poll_budget; /* 1..65535; idle read needs2, idle write needs4. */
    uint8_t active;
    uint8_t last_status;
} hms_avr_eeprom;

void hms_avr_eeprom_init(hms_avr_eeprom *driver, uint16_t poll_budget);
uint8_t hms_avr_eeprom_read_byte(void *user, uint32_t address, uint8_t *value);
uint8_t hms_avr_eeprom_program_zero_and_sync(void *user, uint32_t address);

#endif
