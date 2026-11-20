#ifndef HMS_BOOT_EPOCH_H
#define HMS_BOOT_EPOCH_H

#include <stdint.h>

#define HMS_BOOT_HEADER_BYTES 32u

enum hms_boot_status {
    HMS_BOOT_RESERVED, HMS_BOOT_UNATTEMPTED, HMS_BOOT_IN_PROGRESS,
    HMS_BOOT_BAD_CONFIG, HMS_BOOT_STORAGE_ERROR, HMS_BOOT_HEADER_MISMATCH,
    HMS_BOOT_NONPREFIX, HMS_BOOT_EXHAUSTED, HMS_BOOT_VERIFY_FAILED
};

/* A deliberately finite reservation bank. This is not electrical storage
 * qualification. Before using its result as an endpoint boot epoch, a platform
 * must establish all of the following for the entire enrolled incarnation:
 * - exclusive ownership, immutable configuration and bounded callbacks;
 * - reads return durable bytes or report failure (never fabricated values);
 * - program_zero_and_sync touches only its selected byte, and success means
 *   durable completion, including any controller/cache/bus completion;
 * - a failed/interrupted write may leave ANY value in that byte; previously
 *   completed bytes and the provisioned header remain stable;
 * - no erasure, rollback, restoration or rewrite of consumed cells.
 * Brownout/CPU-address corruption and retention faults require separate
 * platform engineering. A highest consumed byte reverting to 0xff is not
 * detectable in this model. CRC/readback would not establish rollback immunity.
 *
 * region_base..region_base+32+capacity-1 is one installed storage region.
 * The exact header is factory-provisioned; this API never formats or repairs it.
 * Incarnation bytes must agree with the endpoint's enrolled incarnation and be
 * immutable. Exhaustion requires explicit recommissioning with a NEW incarnation
 * or a separately qualified profile, never wrapping/erasing this bank in place.
 */
typedef struct {
    void *user;
    uint8_t (*read_byte)(void *user, uint32_t address, uint8_t *value);
    uint8_t (*program_zero_and_sync)(void *user, uint32_t address);
    uint8_t (*incarnation_byte)(void *user, uint8_t index);
    uint32_t region_base;
    uint16_t capacity; /* 1..65535 reservations, one byte each. */
} hms_boot_storage;

/* One serialized startup owner. RAM reset/init is permitted only at the boot
 * boundary, before any ordinary endpoint activity. No ISR/concurrent access.
 * An attempt is latched before callbacks; retries return that same result.
 */
typedef struct {
    const hms_boot_storage *owner;
    uint64_t epoch;
    uint8_t attempted;
    uint8_t status;
} hms_boot_reservation;

void hms_boot_init(hms_boot_reservation *reservation);
uint8_t hms_boot_header_byte(const hms_boot_storage *storage, uint8_t index);
uint8_t hms_boot_acquire(hms_boot_reservation *reservation, const hms_boot_storage *storage);
uint64_t hms_boot_reserved_epoch(const hms_boot_reservation *reservation);

#endif
