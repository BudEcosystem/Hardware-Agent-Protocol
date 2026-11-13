#include "bhms_hal_host.h"

#include <string.h>

static int h_read(void *ctx) {
    bhms_host *h = (bhms_host *)ctx;
    if (h->rx_len == 0) return -1;
    {
        int c = h->rx[h->rx_head];
        h->rx_head = (h->rx_head + 1u) % BHMS_HOST_RX_CAP;
        --h->rx_len;
        return c;
    }
}

static void h_write(void *ctx, const uint8_t *buf, size_t n) {
    bhms_host *h = (bhms_host *)ctx;
    if (h->tx_len + n > BHMS_HOST_TX_CAP) n = BHMS_HOST_TX_CAP - h->tx_len; /* drop overflow */
    memcpy(h->tx + h->tx_len, buf, n);
    h->tx_len += n;
    if (h->tx_per_millis != 0) h->now_ms += (uint32_t)h->tx_per_millis;
}

static uint32_t h_millis(void *ctx) { return ((bhms_host *)ctx)->now_ms; }

static int h_pin(void *ctx) { return ((bhms_host *)ctx)->pin; }

static int h_epoch_load(void *ctx, uint32_t *epoch) {
    bhms_host *h = (bhms_host *)ctx;
    if (!h->has_eeprom) return -1;
    *epoch = h->eeprom == 0xFFFFFFFFu ? 0u : h->eeprom;
    return 0;
}

static int h_epoch_store(void *ctx, uint32_t epoch) {
    bhms_host *h = (bhms_host *)ctx;
    if (!h->has_eeprom || h->store_fails) return -1;
    h->eeprom = epoch;
    ++h->eeprom_writes;
    return 0;
}

void bhms_host_init(bhms_host *h, int persistent_epoch) {
    memset(h, 0, sizeof *h);
    h->has_eeprom = persistent_epoch;
    h->eeprom = 0xFFFFFFFFu; /* erased */
    h->hal.ctx = h;
    h->hal.uart_read = h_read;
    h->hal.uart_write = h_write;
    h->hal.millis = h_millis;
    h->hal.stop_pin = h_pin;
    if (persistent_epoch) {
        h->hal.epoch_load = h_epoch_load;
        h->hal.epoch_store = h_epoch_store;
    }
}

int bhms_host_feed(bhms_host *h, const uint8_t *bytes, size_t n) {
    size_t i;
    if (h->rx_len + n > BHMS_HOST_RX_CAP) return -1;
    for (i = 0; i < n; ++i) h->rx[(h->rx_head + h->rx_len++) % BHMS_HOST_RX_CAP] = bytes[i];
    return 0;
}

int bhms_host_feed_frame(bhms_host *h, uint8_t kind, uint8_t channel, uint64_t session,
                         uint32_t sequence, const uint8_t *payload, size_t n) {
    uint8_t wire[HMS_FRAME_WIRE_MAX];
    size_t w = bhms_frame_encode(wire, sizeof wire, kind, channel, session, sequence, payload, n);
    if (w == 0) return -1;
    return bhms_host_feed(h, wire, w);
}

size_t bhms_host_tx_pending(const bhms_host *h) { return h->tx_len - h->tx_read; }

int bhms_host_next_tx(bhms_host *h, bhms_host_frame *out) {
    hms_frame_parser p;
    hms_frame_reset(&p);
    while (h->tx_read < h->tx_len) {
        hms_frame_result r = hms_frame_feed(&p, h->tx[h->tx_read++]);
        if (r == HMS_FRAME_READY) {
            unsigned i;
            out->kind = p.raw[3];
            out->channel = p.raw[5];
            out->session = 0;
            for (i = 0; i < 8u; ++i) out->session = (out->session << 8) | p.raw[6 + i];
            out->sequence = ((uint32_t)p.raw[14] << 24) | ((uint32_t)p.raw[15] << 16) |
                            ((uint32_t)p.raw[16] << 8) | p.raw[17];
            out->length = (uint16_t)(((uint16_t)p.raw[18] << 8) | p.raw[19]);
            memcpy(out->payload, p.raw + HMS_FRAME_HEADER, out->length);
            return 1;
        }
        if (r == HMS_FRAME_INVALID || r == HMS_FRAME_OVERFLOW) return -1;
    }
    return 0;
}
