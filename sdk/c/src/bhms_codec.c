/* BHMS-Compact message and value codecs (spec/bhms/11-compact-binding.md 11.2, 11.4). */
#include <string.h>

#include "bhms.h"

static void put16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }

static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

uint8_t bhms_type_width(uint8_t type) {
    switch (type) {
    case BHMS_U8: case BHMS_I8: case BHMS_BOOL: return 1;
    case BHMS_U16: case BHMS_I16: return 2;
    case BHMS_U32: case BHMS_I32: case BHMS_F32: return 4;
    default: return 0;
    }
}

void bhms_value_put(uint8_t type, bhms_value v, uint8_t *out) {
    switch (type) {
    case BHMS_U8: case BHMS_I8: case BHMS_BOOL: out[0] = (uint8_t)v.u; break;
    case BHMS_U16: case BHMS_I16: put16(out, (uint16_t)v.u); break;
    case BHMS_F32: {
        uint32_t bits;
        memcpy(&bits, &v.f, sizeof bits);
        put32(out, bits);
        break;
    }
    default: put32(out, v.u); break; /* U32, I32 */
    }
}

int bhms_value_get(uint8_t type, const uint8_t *in, bhms_value *out) {
    out->u = 0;
    switch (type) {
    case BHMS_U8: out->u = in[0]; return 0;
    case BHMS_I8: out->i = (int8_t)in[0]; return 0;
    case BHMS_BOOL:
        if (in[0] > 1u) return -1;
        out->u = in[0];
        return 0;
    case BHMS_U16: out->u = get16(in); return 0;
    case BHMS_I16: out->i = (int16_t)get16(in); return 0;
    case BHMS_U32: out->u = get32(in); return 0;
    case BHMS_I32: out->i = (int32_t)get32(in); return 0;
    case BHMS_F32: {
        uint32_t bits = get32(in);
        memcpy(&out->f, &bits, sizeof bits);
        return 0;
    }
    default: return -1;
    }
}

size_t bhms_enc_hello_req(uint8_t *b, uint8_t flags, uint32_t nonce) {
    b[0] = BHMS_MSG_HELLO_REQ;
    b[1] = BHMS_VERSION;
    b[2] = flags;
    put32(b + 3, nonce);
    return BHMS_LEN_HELLO_REQ;
}

size_t bhms_enc_hello(uint8_t *b, uint8_t flags, const uint8_t digest8[8], uint32_t epoch,
                      uint32_t nonce, uint16_t last_handle, uint8_t ring, uint8_t max_active,
                      uint8_t max_args) {
    b[0] = BHMS_MSG_HELLO;
    b[1] = BHMS_VERSION;
    b[2] = flags;
    memcpy(b + 3, digest8, 8);
    put32(b + 11, epoch);
    put32(b + 15, nonce);
    put16(b + 19, last_handle);
    b[21] = ring;
    b[22] = max_active;
    b[23] = max_args;
    return BHMS_LEN_HELLO;
}

size_t bhms_enc_invoke(uint8_t *b, uint16_t handle, uint8_t action, uint32_t fence,
                       uint16_t ttl_ms, const uint8_t *args, size_t n_args) {
    b[0] = BHMS_MSG_INVOKE;
    put16(b + 1, handle);
    b[3] = action;
    put32(b + 4, fence);
    put16(b + 8, ttl_ms);
    if (n_args != 0) memcpy(b + BHMS_LEN_INVOKE_FIXED, args, n_args);
    return BHMS_LEN_INVOKE_FIXED + n_args;
}

size_t bhms_enc_cancel(uint8_t *b, uint16_t handle) {
    b[0] = BHMS_MSG_CANCEL;
    put16(b + 1, handle);
    return BHMS_LEN_CANCEL;
}

size_t bhms_enc_query(uint8_t *b, uint16_t handle) {
    b[0] = BHMS_MSG_QUERY;
    put16(b + 1, handle);
    return BHMS_LEN_QUERY;
}

size_t bhms_enc_read(uint8_t *b, uint16_t request, uint8_t property, uint8_t flags) {
    b[0] = BHMS_MSG_READ;
    put16(b + 1, request);
    b[3] = property;
    b[4] = flags;
    return BHMS_LEN_READ;
}

size_t bhms_enc_stop(uint8_t *b, uint8_t reason) {
    b[0] = BHMS_MSG_STOP;
    b[1] = reason;
    return BHMS_LEN_STOP;
}

size_t bhms_enc_status(uint8_t *b, uint16_t handle, uint8_t state, uint8_t cancel,
                       uint8_t progress) {
    b[0] = BHMS_MSG_STATUS;
    put16(b + 1, handle);
    b[3] = state;
    b[4] = cancel;
    b[5] = progress;
    return BHMS_LEN_STATUS;
}

size_t bhms_enc_result(uint8_t *b, uint16_t handle, uint8_t state, uint8_t evidence,
                       uint8_t fault, const uint8_t *fields, size_t n_fields) {
    b[0] = BHMS_MSG_RESULT;
    put16(b + 1, handle);
    b[3] = state;
    b[4] = evidence;
    b[5] = fault;
    if (n_fields != 0) memcpy(b + BHMS_LEN_RESULT_FIXED, fields, n_fields);
    return BHMS_LEN_RESULT_FIXED + n_fields;
}

size_t bhms_enc_value(uint8_t *b, uint16_t request, uint8_t property, uint8_t quality,
                      uint8_t evidence, uint32_t sequence, uint32_t age_ms,
                      const uint8_t *value, size_t n_value) {
    b[0] = BHMS_MSG_VALUE;
    put16(b + 1, request);
    b[3] = property;
    b[4] = quality;
    b[5] = evidence;
    put32(b + 6, sequence);
    put32(b + 10, age_ms);
    if (n_value != 0) memcpy(b + BHMS_LEN_VALUE_FIXED, value, n_value);
    return BHMS_LEN_VALUE_FIXED + n_value;
}

size_t bhms_enc_stop_ack(uint8_t *b, uint8_t outcome, uint8_t evidence, uint8_t canceled) {
    b[0] = BHMS_MSG_STOP_ACK;
    b[1] = outcome;
    b[2] = evidence;
    b[3] = canceled;
    return BHMS_LEN_STOP_ACK;
}

size_t bhms_enc_error(uint8_t *b, uint8_t request_type, uint16_t id, uint8_t code,
                      uint8_t detail) {
    b[0] = BHMS_MSG_ERROR;
    b[1] = request_type;
    put16(b + 2, id);
    b[4] = code;
    b[5] = detail;
    return BHMS_LEN_ERROR;
}

int bhms_dec_hello_req(const uint8_t *p, size_t n, bhms_hello_req *o) {
    if (n != BHMS_LEN_HELLO_REQ || p[0] != BHMS_MSG_HELLO_REQ) return -1;
    o->version = p[1];
    o->flags = p[2];
    o->nonce = get32(p + 3);
    return 0;
}

int bhms_dec_hello(const uint8_t *p, size_t n, bhms_hello *o) {
    if (n != BHMS_LEN_HELLO || p[0] != BHMS_MSG_HELLO) return -1;
    o->version = p[1];
    o->flags = p[2];
    memcpy(o->digest8, p + 3, 8);
    o->epoch = get32(p + 11);
    o->nonce = get32(p + 15);
    o->last_handle = get16(p + 19);
    o->ring = p[21];
    o->max_active = p[22];
    o->max_args = p[23];
    return 0;
}

int bhms_dec_invoke(const uint8_t *p, size_t n, bhms_invoke *o) {
    if (n < BHMS_LEN_INVOKE_FIXED || p[0] != BHMS_MSG_INVOKE) return -1;
    o->handle = get16(p + 1);
    o->action = p[3];
    o->fence = get32(p + 4);
    o->ttl_ms = get16(p + 8);
    o->args = p + BHMS_LEN_INVOKE_FIXED;
    o->n_args = n - BHMS_LEN_INVOKE_FIXED;
    return 0;
}

int bhms_dec_status(const uint8_t *p, size_t n, bhms_status *o) {
    if (n != BHMS_LEN_STATUS || p[0] != BHMS_MSG_STATUS) return -1;
    o->handle = get16(p + 1);
    o->state = p[3];
    o->cancel = p[4];
    o->progress = p[5];
    return 0;
}

int bhms_dec_result(const uint8_t *p, size_t n, bhms_result *o) {
    if (n < BHMS_LEN_RESULT_FIXED || p[0] != BHMS_MSG_RESULT) return -1;
    o->handle = get16(p + 1);
    o->state = p[3];
    o->evidence = p[4];
    o->fault = p[5];
    o->fields = p + BHMS_LEN_RESULT_FIXED;
    o->n_fields = n - BHMS_LEN_RESULT_FIXED;
    return 0;
}

int bhms_dec_value(const uint8_t *p, size_t n, bhms_valuemsg *o) {
    if (n < BHMS_LEN_VALUE_FIXED || p[0] != BHMS_MSG_VALUE) return -1;
    o->request = get16(p + 1);
    o->property = p[3];
    o->quality = p[4];
    o->evidence = p[5];
    o->sequence = get32(p + 6);
    o->age_ms = get32(p + 10);
    o->value = p + BHMS_LEN_VALUE_FIXED;
    o->n_value = n - BHMS_LEN_VALUE_FIXED;
    return 0;
}

int bhms_dec_stop_ack(const uint8_t *p, size_t n, bhms_stop_ack *o) {
    if (n != BHMS_LEN_STOP_ACK || p[0] != BHMS_MSG_STOP_ACK) return -1;
    o->outcome = p[1];
    o->evidence = p[2];
    o->canceled = p[3];
    return 0;
}

int bhms_dec_error(const uint8_t *p, size_t n, bhms_error *o) {
    if (n != BHMS_LEN_ERROR || p[0] != BHMS_MSG_ERROR) return -1;
    o->request_type = p[1];
    o->id = get16(p + 2);
    o->code = p[4];
    o->detail = p[5];
    return 0;
}
