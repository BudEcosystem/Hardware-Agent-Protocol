/* Frame encoder for the `HM` frame (protocol/serial/frame.py `encode`).
 *
 * protocol/serial/frame.c is decode-only, and its FCS routine is file-static, so
 * the transmit side lives here: the same header layout, polynomial 0x8408 and
 * byte stuffing as frame.py. Tests cross-check every emitted frame through the
 * reused hms_frame_parser and the Python encoder's vectors. */
#include "bhms.h"

#define FLAG 0x7Eu
#define ESC 0x7Du

typedef struct {
    uint8_t *out; /* host mode: whole frame buffer */
    size_t cap, len;
    const bhms_hal *hal; /* embedded mode: chunked stream */
    uint8_t chunk[24];
    uint8_t chunk_len;
    uint16_t crc;
    uint8_t overflow;
} txs;

static void tx_raw(txs *t, uint8_t b) {
    if (t->hal != 0) {
        t->chunk[t->chunk_len++] = b;
        if (t->chunk_len == sizeof t->chunk) {
            t->hal->uart_write(t->hal->ctx, t->chunk, t->chunk_len);
            t->chunk_len = 0;
        }
    } else if (t->len < t->cap) {
        t->out[t->len++] = b;
    } else {
        t->overflow = 1;
    }
}

static void tx_stuffed(txs *t, uint8_t b) {
    if (b == FLAG || b == ESC) {
        tx_raw(t, ESC);
        tx_raw(t, (uint8_t)(b ^ 0x20u));
    } else {
        tx_raw(t, b);
    }
}

/* Raw frame byte: update FCS, then emit stuffed. */
static void tx_byte(txs *t, uint8_t b) {
    uint8_t bit;
    t->crc = (uint16_t)(t->crc ^ b);
    for (bit = 0; bit < 8u; ++bit)
        t->crc = (uint16_t)((t->crc >> 1) ^ ((t->crc & 1u) ? 0x8408u : 0u));
    tx_stuffed(t, b);
}

static void tx_frame(txs *t, uint8_t kind, uint8_t channel, uint64_t session, uint32_t seq,
                     const uint8_t *payload, size_t n) {
    uint8_t i;
    uint16_t fcs;
    t->crc = 0xFFFFu;
    tx_raw(t, FLAG);
    tx_byte(t, 'H');
    tx_byte(t, 'M');
    tx_byte(t, 1);
    tx_byte(t, kind);
    tx_byte(t, 0);
    tx_byte(t, channel);
    for (i = 0; i < 8u; ++i) tx_byte(t, (uint8_t)(session >> (56u - 8u * i)));
    for (i = 0; i < 4u; ++i) tx_byte(t, (uint8_t)(seq >> (24u - 8u * i)));
    tx_byte(t, (uint8_t)(n >> 8));
    tx_byte(t, (uint8_t)n);
    for (i = 0; i < n; ++i) tx_byte(t, payload[i]);
    fcs = (uint16_t)(t->crc ^ 0xFFFFu);
    tx_stuffed(t, (uint8_t)fcs); /* little-endian, not part of the CRC input */
    tx_stuffed(t, (uint8_t)(fcs >> 8));
    tx_raw(t, FLAG);
}

size_t bhms_frame_encode(uint8_t *out, size_t cap, uint8_t kind, uint8_t channel,
                         uint64_t session, uint32_t sequence, const uint8_t *payload,
                         size_t n_payload) {
    txs t;
    if (out == 0 || n_payload > HMS_FRAME_PAYLOAD || (n_payload != 0 && payload == 0)) return 0;
    t.out = out;
    t.cap = cap;
    t.len = 0;
    t.hal = 0;
    t.chunk_len = 0;
    t.overflow = 0;
    tx_frame(&t, kind, channel, session, sequence, payload, n_payload);
    return t.overflow ? 0 : t.len;
}

void bhms_frame_send(const bhms_hal *hal, uint8_t kind, uint8_t channel, uint64_t session,
                     uint32_t sequence, const uint8_t *payload, size_t n_payload) {
    txs t;
    if (n_payload > HMS_FRAME_PAYLOAD) return;
    t.out = 0;
    t.cap = t.len = 0;
    t.hal = hal;
    t.chunk_len = 0;
    t.overflow = 0;
    tx_frame(&t, kind, channel, session, sequence, payload, n_payload);
    if (t.chunk_len != 0) hal->uart_write(hal->ctx, t.chunk, t.chunk_len);
}
