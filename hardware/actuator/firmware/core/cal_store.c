#include "cal_store.h"

#include <string.h>

void cal_store_init(cal_store *s, const epoch_flash_ops *ops) {
    reclog_init(&s->log, ops, CAL_MAGIC, (uint8_t)CAL_PAYLOAD_BYTES);
}

int cal_store_load(const cal_store *s, arm_cal *out) {
    uint8_t p[CAL_PAYLOAD_BYTES];
    uint32_t seq;
    unsigned i;
    if (!reclog_latest(&s->log, &seq, p)) return 0;
    for (i = 0; i < ARM_NUM_SERVOS; ++i) {
        out->raw_zero[i] = (int16_t)(uint16_t)(p[2u * i] | (p[2u * i + 1u] << 8));
        out->sign[i] = (int8_t)p[2u * ARM_NUM_SERVOS + i];
        if (out->sign[i] != 1 && out->sign[i] != -1) return 0;
    }
    return 1;
}

int cal_store_save(const cal_store *s, const arm_cal *cal) {
    uint8_t p[CAL_PAYLOAD_BYTES];
    uint32_t seq = 0;
    unsigned i;
    for (i = 0; i < ARM_NUM_SERVOS; ++i) {
        p[2u * i] = (uint8_t)((uint16_t)cal->raw_zero[i] & 0xFFu);
        p[2u * i + 1u] = (uint8_t)((uint16_t)cal->raw_zero[i] >> 8);
        p[2u * ARM_NUM_SERVOS + i] = (uint8_t)cal->sign[i];
    }
    (void)reclog_latest(&s->log, &seq, 0);
    return reclog_append(&s->log, seq + 1u, p);
}
