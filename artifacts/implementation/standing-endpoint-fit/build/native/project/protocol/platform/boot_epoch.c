#include "boot_epoch.h"
#include <stddef.h>

void hms_boot_init(hms_boot_reservation *r) {
    if (r == NULL) return;
    r->owner = NULL; r->epoch = 0; r->attempted = 0; r->status = HMS_BOOT_UNATTEMPTED;
}

uint8_t hms_boot_header_byte(const hms_boot_storage *s, uint8_t index) {
    /* Format v1: ASCII HMSBOOT1, incarnation16, capacity big endian, reserved0. */
    static const uint8_t magic[8] = {'H','M','S','B','O','O','T','1'};
    if (s == NULL || s->incarnation_byte == NULL || index >= HMS_BOOT_HEADER_BYTES) return 0;
    if (index < 8u) return magic[index];
    if (index < 24u) return s->incarnation_byte(s->user, (uint8_t)(index - 8u));
    if (index == 24u) return (uint8_t)(s->capacity >> 8);
    if (index == 25u) return (uint8_t)s->capacity;
    return 0;
}

uint8_t hms_boot_acquire(hms_boot_reservation *r, const hms_boot_storage *s) {
    uint32_t index, first_erased, address;
    uint8_t value, incarnation_nonzero = 0;
    if (r == NULL) return HMS_BOOT_BAD_CONFIG;
    if (r->attempted != 0u)
        return s == r->owner ? r->status : HMS_BOOT_BAD_CONFIG;
    r->attempted = 1; r->owner = s; r->epoch = 0; r->status = HMS_BOOT_IN_PROGRESS;
    if (s == NULL || s->read_byte == NULL || s->program_zero_and_sync == NULL ||
        s->incarnation_byte == NULL || s->capacity == 0u ||
        s->region_base > UINT32_MAX - HMS_BOOT_HEADER_BYTES - ((uint32_t)s->capacity - 1u)) {
        r->status = HMS_BOOT_BAD_CONFIG; return r->status;
    }
    for (index = 0; index < 16u; ++index)
        incarnation_nonzero |= s->incarnation_byte(s->user, (uint8_t)index);
    if (incarnation_nonzero == 0u) { r->status = HMS_BOOT_BAD_CONFIG; return r->status; }
    for (index = 0; index < HMS_BOOT_HEADER_BYTES; ++index) {
        if (s->read_byte(s->user, s->region_base + index, &value) != 1u) {
            r->status = HMS_BOOT_STORAGE_ERROR; return r->status;
        }
        if (value != hms_boot_header_byte(s, (uint8_t)index)) {
            r->status = HMS_BOOT_HEADER_MISMATCH; return r->status;
        }
    }
    first_erased = s->capacity;
    for (index = 0; index < s->capacity; ++index) {
        address = s->region_base + HMS_BOOT_HEADER_BYTES + index;
        if (s->read_byte(s->user, address, &value) != 1u) {
            r->status = HMS_BOOT_STORAGE_ERROR; return r->status;
        }
        if (value == 0xffu) {
            if (first_erased == s->capacity) first_erased = index;
        } else if (first_erased != s->capacity) {
            r->status = HMS_BOOT_NONPREFIX; return r->status;
        }
    }
    if (first_erased == s->capacity) { r->status = HMS_BOOT_EXHAUSTED; return r->status; }
    address = s->region_base + HMS_BOOT_HEADER_BYTES + first_erased;
    if (s->program_zero_and_sync(s->user, address) != 1u ||
        s->read_byte(s->user, address, &value) != 1u) {
        r->status = HMS_BOOT_STORAGE_ERROR; return r->status;
    }
    if (value != 0u) { r->status = HMS_BOOT_VERIFY_FAILED; return r->status; }
    r->epoch = (uint64_t)first_erased + 1u;
    r->status = HMS_BOOT_RESERVED;
    return r->status;
}

uint64_t hms_boot_reserved_epoch(const hms_boot_reservation *r) {
    if (r == NULL || r->attempted == 0u || r->status != HMS_BOOT_RESERVED) return 0;
    return r->epoch;
}
