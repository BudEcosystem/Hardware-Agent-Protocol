#include "sts.h"

#include <string.h>

uint8_t sts_checksum(const uint8_t *p, size_t n) {
    unsigned sum = 0;
    size_t i;
    for (i = 0; i < n; ++i) sum += p[i];
    return (uint8_t)(~sum & 0xFFu);
}

size_t sts_encode(uint8_t *out, size_t cap, uint8_t id, uint8_t instr, const uint8_t *params,
                  size_t n_params) {
    size_t total = n_params + 6u;
    if (out == 0 || n_params > STS_MAX_PARAMS || cap < total || (n_params != 0 && params == 0))
        return 0;
    out[0] = 0xFF;
    out[1] = 0xFF;
    out[2] = id;
    out[3] = (uint8_t)(n_params + 2u);
    out[4] = instr;
    if (n_params != 0) memcpy(&out[5], params, n_params);
    out[5 + n_params] = sts_checksum(&out[2], n_params + 3u);
    return total;
}

size_t sts_encode_sync_write(uint8_t *out, size_t cap, uint8_t addr, uint8_t per_len, size_t n,
                             const uint8_t *ids, const uint8_t *data) {
    uint8_t params[STS_MAX_PARAMS];
    size_t i, k = 0;
    if (n == 0 || per_len == 0 || ids == 0 || data == 0) return 0;
    if (2u + n * ((size_t)per_len + 1u) > STS_MAX_PARAMS) return 0;
    params[k++] = addr;
    params[k++] = per_len;
    for (i = 0; i < n; ++i) {
        params[k++] = ids[i];
        memcpy(&params[k], &data[i * per_len], per_len);
        k += per_len;
    }
    return sts_encode(out, cap, STS_BROADCAST_ID, STS_INSTR_SYNC_WRITE, params, k);
}

int sts_decode(const uint8_t *buf, size_t n, sts_status *out) {
    size_t len, np;
    if (n < 6u) return STS_E_SHORT;
    if (buf[0] != 0xFF || buf[1] != 0xFF) return STS_E_HEADER;
    len = buf[3];
    if (len < 2u || len - 2u > STS_MAX_PARAMS) return STS_E_LENGTH;
    if (n < len + 4u) return STS_E_SHORT;
    if (sts_checksum(&buf[2], len + 1u) != buf[len + 3u]) return STS_E_CHECKSUM;
    np = len - 2u;
    out->id = buf[2];
    out->error = buf[4];
    out->n = (uint8_t)np;
    memcpy(out->params, &buf[5], np);
    return STS_OK;
}

uint16_t sts_get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
void sts_put16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)(v >> 8);
}
int32_t sts_sm_decode(uint16_t raw, unsigned sign_bit) {
    int32_t mag = (int32_t)(raw & ((1u << sign_bit) - 1u));
    return (raw & (1u << sign_bit)) != 0 ? -mag : mag;
}
uint16_t sts_sm_encode(int32_t v, unsigned sign_bit) {
    uint32_t mag = (uint32_t)(v < 0 ? -v : v) & ((1u << sign_bit) - 1u);
    return (uint16_t)(mag | (v < 0 ? (1u << sign_bit) : 0u));
}

/* ---- Bus ---------------------------------------------------------------------- */
void sts_bus_init(sts_bus *bus, const arm_hw *hw) {
    memset(bus, 0, sizeof *bus);
    bus->hw = hw;
}

int sts_bus_xfer(sts_bus *bus, uint8_t id, uint8_t instr, const uint8_t *params, size_t n_params,
                 sts_status *reply) {
    uint8_t tx[STS_FRAME_MAX], echo[STS_FRAME_MAX], rx[STS_FRAME_MAX + 2u];
    size_t n = sts_encode(tx, sizeof tx, id, instr, params, n_params);
    size_t got, need;
    int rc;
    if (n == 0) return STSB_ARG;
    bus->hw->bus_flush(bus->hw->ctx);
    bus->hw->bus_write(bus->hw->ctx, tx, n);
    ++bus->frames;
    /* The RX buffer is always enabled, so the UART saw its own bytes: discard exactly
     * n of them and compare (INTERFACE.md section 3, step 5). */
    got = bus->hw->bus_read(bus->hw->ctx, echo, n, STS_ECHO_TIMEOUT_US);
    if (got != n || memcmp(echo, tx, n) != 0) {
        ++bus->collisions;
        return STSB_COLLISION;
    }
    if (reply == 0 || id == STS_BROADCAST_ID) return STSB_OK;
    got = bus->hw->bus_read(bus->hw->ctx, rx, 4, STS_REPLY_TIMEOUT_US);
    if (got < 4u) {
        ++bus->timeouts;
        return STSB_TIMEOUT;
    }
    if (rx[0] != 0xFF || rx[1] != 0xFF || rx[3] < 2u || rx[3] - 2u > STS_MAX_PARAMS) {
        ++bus->bad_replies;
        return STSB_BAD_REPLY;
    }
    need = (size_t)rx[3];
    got = bus->hw->bus_read(bus->hw->ctx, &rx[4], need, STS_REPLY_TIMEOUT_US);
    if (got < need) {
        ++bus->timeouts;
        return STSB_TIMEOUT;
    }
    rc = sts_decode(rx, need + 4u, reply);
    if (rc != STS_OK || reply->id != id) {
        ++bus->bad_replies;
        return STSB_BAD_REPLY;
    }
    return STSB_OK;
}

int sts_bus_ping(sts_bus *bus, uint8_t id, sts_status *reply) {
    sts_status local;
    return sts_bus_xfer(bus, id, STS_INSTR_PING, 0, 0, reply != 0 ? reply : &local);
}

int sts_bus_read(sts_bus *bus, uint8_t id, uint8_t addr, uint8_t len, uint8_t *out,
                 uint8_t *servo_error) {
    uint8_t p[2];
    sts_status st;
    int rc;
    if (len == 0 || len > STS_MAX_PARAMS || out == 0) return STSB_ARG;
    p[0] = addr;
    p[1] = len;
    rc = sts_bus_xfer(bus, id, STS_INSTR_READ, p, 2, &st);
    if (rc != STSB_OK) return rc;
    if (st.n != len) {
        ++bus->bad_replies;
        return STSB_BAD_REPLY;
    }
    memcpy(out, st.params, len);
    if (servo_error != 0) *servo_error = st.error;
    return STSB_OK;
}

int sts_bus_write(sts_bus *bus, uint8_t id, uint8_t addr, const uint8_t *data, size_t len) {
    uint8_t p[STS_MAX_PARAMS];
    sts_status st;
    if (id == STS_BROADCAST_ID || len == 0 || len + 1u > STS_MAX_PARAMS || data == 0)
        return STSB_ARG;
    p[0] = addr;
    memcpy(&p[1], data, len);
    return sts_bus_xfer(bus, id, STS_INSTR_WRITE, p, len + 1u, &st);
}

int sts_bus_sync_write(sts_bus *bus, uint8_t addr, uint8_t per_len, size_t n, const uint8_t *ids,
                       const uint8_t *data) {
    uint8_t frame[STS_FRAME_MAX];
    size_t len = sts_encode_sync_write(frame, sizeof frame, addr, per_len, n, ids, data);
    if (len == 0) return STSB_ARG;
    /* Re-use the transaction path so echo checking applies: split the frame into
     * (instr, params). */
    return sts_bus_xfer(bus, STS_BROADCAST_ID, STS_INSTR_SYNC_WRITE, &frame[5], len - 6u, 0);
}
