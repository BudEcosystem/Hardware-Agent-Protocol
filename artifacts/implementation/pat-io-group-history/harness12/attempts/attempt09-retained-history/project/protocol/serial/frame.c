#include "frame.h"

static uint16_t fcs(const uint8_t *data, uint16_t length) {
    uint16_t crc = UINT16_C(0xffff);
    uint16_t i;
    for (i = 0; i < length; ++i) {
        uint8_t bit;
        crc = (uint16_t)(crc ^ data[i]);
        for (bit = 0; bit < 8u; ++bit) {
            crc = (uint16_t)((crc >> 1) ^ ((crc & 1u) ? UINT16_C(0x8408) : 0u));
        }
    }
    return crc;
}

static int valid(const hms_frame_parser *p) {
    uint16_t payload_length;
    if (p->length < HMS_FRAME_HEADER + 2u || p->length > HMS_FRAME_RAW) return 0;
    if (p->raw[0] != 'H' || p->raw[1] != 'M' || p->raw[2] != 1u ||
        p->raw[3] < 1u || p->raw[3] > 4u || p->raw[4] != 0u) return 0;
    payload_length = (uint16_t)(((uint16_t)p->raw[18] << 8) | p->raw[19]);
    if (payload_length > HMS_FRAME_PAYLOAD ||
        p->length != HMS_FRAME_HEADER + payload_length + 2u) return 0;
    return fcs(p->raw, p->length) == UINT16_C(0xf0b8);
}

void hms_frame_reset(hms_frame_parser *p) {
    p->length = 0;
    p->active = p->escaped = p->discarding = 0;
}

hms_frame_result hms_frame_feed(hms_frame_parser *p, uint8_t byte) {
    hms_frame_result result = HMS_FRAME_NONE;
    if (byte == 0x7eu) {
        if (p->active && !p->discarding) {
            if (p->escaped) result = HMS_FRAME_INVALID;
            else if (p->length) result = valid(p) ? HMS_FRAME_READY : HMS_FRAME_INVALID;
        }
        /* Retain raw bytes on READY for the caller; only length is reset. */
        p->length = 0;
        p->active = 1;
        p->escaped = p->discarding = 0;
        return result;
    }
    if (!p->active || p->discarding) return HMS_FRAME_NONE;
    if (p->escaped) {
        byte ^= 0x20u;
        p->escaped = 0;
    } else if (byte == 0x7du) {
        p->escaped = 1;
        return HMS_FRAME_NONE;
    }
    if (p->length == HMS_FRAME_RAW) {
        p->length = 0;
        p->discarding = 1;
        return HMS_FRAME_OVERFLOW;
    }
    p->raw[p->length++] = byte;
    return HMS_FRAME_NONE;
}
