#include "link.h"
#include <string.h>

static uint32_t read32(const uint8_t *p) {
    uint8_t i; uint32_t value = 0;
    for (i = 0; i < 4u; ++i) value = (value << 8) | p[i];
    return value;
}
static uint64_t read64(const uint8_t *p) {
    uint8_t i; uint64_t value = 0;
    for (i = 0; i < 8u; ++i) value = (value << 8) | p[i];
    return value;
}
static void write32(uint8_t *p, uint32_t v) {
    uint8_t i; for (i = 0; i < 4u; ++i) { p[3u-i] = (uint8_t)v; v >>= 8; }
}
static void write64(uint8_t *p, uint64_t v) {
    uint8_t i; for (i = 0; i < 8u; ++i) { p[7u-i] = (uint8_t)v; v >>= 8; }
}
static uint16_t fcs(const uint8_t *p, uint16_t n) {
    uint16_t crc = UINT16_C(0xffff), i;
    for (i = 0; i < n; ++i) {
        uint8_t bit; crc ^= p[i];
        for (bit = 0; bit < 8u; ++bit) crc = (uint16_t)((crc >> 1) ^ ((crc & 1u) != 0u ? UINT16_C(0x8408) : 0u));
    }
    return (uint16_t)(crc ^ UINT16_C(0xffff));
}
void hms_endpoint_link_init(hms_endpoint_link *l) { memset(l, 0, sizeof(*l)); l->receive_budget_ms = 1000; hms_frame_reset(&l->parser); }
void hms_endpoint_link_reset_receive(hms_endpoint_link *l) { hms_frame_reset(&l->parser); l->receive_partial = 0; }
uint8_t hms_endpoint_link_set_receive_budget(hms_endpoint_link *l, uint32_t ms) {
    if (ms == 0u || ms > UINT32_C(0x7fffffff)) return 0;
    hms_endpoint_link_reset_receive(l); l->receive_budget_ms = ms; return 1;
}
void hms_endpoint_link_check_deadline(hms_endpoint_link *l, uint64_t now) {
    if (l->receive_partial != 0u && (now == UINT64_MAX || now < l->receive_started ||
            now - l->receive_started >= l->receive_budget_ms)) hms_endpoint_link_reset_receive(l);
}
void hms_endpoint_link_before_feed(hms_endpoint_link *l, uint8_t byte, uint64_t now) {
    hms_endpoint_link_check_deadline(l, now);
    if (byte != 0x7eu && l->parser.active != 0u && l->receive_partial == 0u) {
        l->receive_partial = 1; l->receive_started = now;
    }
    if (byte == 0x7eu) l->receive_partial = 0;
}
void hms_endpoint_link_accept_ready(hms_endpoint_link *l, hms_endpoint *e,
                                    uint64_t now, uint16_t flags) {
    uint16_t length, response_length = 0, crc;
    uint8_t *p;
    p = l->parser.raw;
    length = (uint16_t)(((uint16_t)p[18] << 8) | p[19]);
    if (l->transmit_phase != 0u) {
        if (length >= 2u && ((p[20] == 1u && (p[21] == 0x22u || p[21] == 0x12u)) ||
                (p[20] == 2u && (p[21] == 0x47u || p[21] == 0x45u || p[21] == 0x12u))))
            (void)hms_endpoint_handle(e, p[3], p[5], read64(p + 6), read32(p + 14),
                                      p + 20, length, now, flags, NULL, &response_length);
        return;
    }
    if (hms_endpoint_handle(e, p[3], p[5], read64(p + 6), read32(p + 14), p + 20,
                            length, now, flags, l->transmit + 20, &response_length) == 0u) return;
    p = l->transmit;
    p[0] = 'H'; p[1] = 'M'; p[2] = 1; p[3] = 2; p[4] = p[5] = 0;
    write64(p + 6, (e->flags & HMS_EP_BOOT_QUALIFIED) != 0u ? e->boot_epoch : 0);
    write32(p + 14, e->response_sequence);
    p[18] = (uint8_t)(response_length >> 8); p[19] = (uint8_t)response_length;
    crc = fcs(p, (uint16_t)(20u + response_length));
    p[20u + response_length] = (uint8_t)crc; p[21u + response_length] = (uint8_t)(crc >> 8);
    l->transmit_length = (uint16_t)(22u + response_length); l->transmit_index = 0;
    l->transmit_phase = 1; l->escape_pending = 0;
}
void hms_endpoint_link_feed(hms_endpoint_link *l, hms_endpoint *e,
                            uint8_t byte, uint64_t now, uint16_t flags) {
    hms_endpoint_link_before_feed(l, byte, now);
    if (hms_frame_feed(&l->parser, byte) == HMS_FRAME_READY)
        hms_endpoint_link_accept_ready(l, e, now, flags);
}
uint8_t hms_endpoint_link_next(hms_endpoint_link *l, uint8_t *byte) {
    uint8_t value;
    if (l->transmit_phase == 0u || byte == NULL) return 0;
    if (l->transmit_phase == 1u) { *byte = 0x7e; l->transmit_phase = 2; return 1; }
    if (l->escape_pending != 0u) { *byte = (uint8_t)(l->escape_pending ^ 0x20u); l->escape_pending = 0; return 1; }
    if (l->transmit_index == l->transmit_length) {
        *byte = 0x7e; l->transmit_phase = 0; return 1;
    }
    value = l->transmit[l->transmit_index++];
    if (value == 0x7e || value == 0x7d) { *byte = 0x7d; l->escape_pending = value; }
    else *byte = value;
    return 1;
}
