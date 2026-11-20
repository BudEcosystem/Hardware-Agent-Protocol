#include "endpoint_fixture.h"
#include <string.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define FIXTURE_FLASH PROGMEM
#else
#define FIXTURE_FLASH
#endif

/* Exact reviewed synthetic fixture values; no firmware/hardware is implied. */
static const uint8_t constants[80] FIXTURE_FLASH = {
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
    0x64, 0xad, 0x21, 0x94, 0xb0, 0x51, 0x50, 0x50, 0xd5, 0x3a, 0xa1, 0xa3, 0x31, 0xe2, 0xe3, 0x37,
    0x18, 0xbb, 0x6f, 0x3d, 0xca, 0x6f, 0xc2, 0x52, 0x5a, 0x1f, 0x23, 0x6b, 0xaa, 0x52, 0xd0, 0xae,
    0xdd, 0xb6, 0x71, 0x4c, 0xa8, 0x81, 0x98, 0x39, 0x41, 0xc5, 0x51, 0x7d, 0x68, 0x47, 0xde, 0x40,
    0x15, 0x0d, 0x5e, 0x47, 0x4f, 0x08, 0xd2, 0x59, 0x58, 0x32, 0x3c, 0x5f, 0xb5, 0x78, 0x93, 0x43,
};
static uint8_t constant_byte(void *user, uint8_t which, uint8_t index) {
    uint8_t offset = which == HMS_EP_INCARNATION ? 0u : (which == HMS_EP_FIRMWARE ? 16u : 48u);
#ifdef __AVR__
    (void)user;
    return pgm_read_byte(constants + offset + index);
#else
    return ((hms_endpoint_fixture *)user)->constants[offset + index];
#endif
}
static int32_t signed32(const uint8_t *p) {
    uint32_t value = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
    if (value <= INT32_MAX) return (int32_t)value;
    return -1 - (int32_t)(UINT32_MAX - value);
}
static void encode_signed(uint8_t *p, int32_t value) {
    uint32_t u = (uint32_t)value;
    p[0] = (uint8_t)(u >> 24); p[1] = (uint8_t)(u >> 16); p[2] = (uint8_t)(u >> 8); p[3] = (uint8_t)u;
}
static uint8_t describe(void *user, uint16_t primitive, const uint8_t *args,
                        uint8_t length, hms_ep_primitive *d) {
    (void)user;
    d->max_run_ms = 200; d->cancel_supported = 1;
    d->completion_evidence_mask = (uint8_t)(1u << HMS_EP_SIMULATION);
    if (primitive == 0x1234u) {
        int32_t first, second;
        if (length != 8u) return HMS_EP_BAD_ARGUMENT;
        first = signed32(args); second = signed32(args + 4);
        if (first < -100000 || first > 100000 || second < -100000 || second > 100000) return HMS_EP_BAD_ARGUMENT;
        d->resource_mask = 5; d->result_length = 4;
    } else if (primitive == 0x4242u) {
        if (length != 72u) return HMS_EP_BAD_ARGUMENT;
        d->resource_mask = 255; d->result_length = 32;
    } else return HMS_EP_UNKNOWN_PRIMITIVE;
    return HMS_EP_OK;
}
static uint8_t guard(void *user, uint16_t primitive, const uint8_t *args, uint8_t length) {
    hms_endpoint_fixture *f = user;
    (void)primitive; (void)args; (void)length;
    f->clock_tick += f->guard_advance_ms;
    return f->guard_denied != 0u ? HMS_EP_BAD_STATE : HMS_EP_OK;
}
static uint8_t sample_clock(void *user, uint64_t *tick, uint16_t *flags) {
    hms_endpoint_fixture *f = user;
    *tick = f->clock_tick; *flags = f->platform_flags; return 1;
}
static void complete(hms_endpoint_fixture *f, uint16_t primitive, const uint8_t *args, hms_ep_report *r) {
    ++f->effects; f->active = 0;
    r->terminal_state = HMS_EP_COMPLETED; r->evidence_kind = HMS_EP_SIMULATION;
    if (primitive == 0x1234u) { r->result_length = 4; encode_signed(r->result, f->sum); }
    else { r->result_length = 32; memcpy(r->result, args, 32); }
    if (f->mode == HMS_FIXTURE_FALSE_PHYSICAL) { r->evidence_kind = HMS_EP_PHYSICAL_SENSOR; r->verification = HMS_EP_VERIFIED; }
    if (f->mode == HMS_FIXTURE_OVERSIZE_RESULT) r->result_length = 33;
}
static void step(void *user, uint8_t phase, uint16_t primitive, const uint8_t *args,
                 uint8_t length, uint64_t now, const hms_ep_step_limits *limits, hms_ep_report *r) {
    hms_endpoint_fixture *f = user;
    (void)length; (void)limits;
    if (phase == HMS_EP_START) {
        ++f->dispatches; f->active = 1; f->started = now;
        f->pending_quiescence = primitive == 0x1234u ? 5u : 255u;
        if (primitive == 0x1234u) f->sum = signed32(args) + signed32(args + 4);
    } else if (phase == HMS_EP_QUIESCENCE_STEP) {
        if (f->mode != HMS_FIXTURE_NO_QUIESCENCE) {
            r->quiescent_mask = f->pending_quiescence; f->pending_quiescence = 0;
        }
    } else if (phase == HMS_EP_LOSS_STEP) {
        ++f->loss_steps; f->active = 0;
        r->terminal_state = HMS_EP_FAILED; r->evidence_kind = HMS_EP_SIMULATION;
    } else if (phase == HMS_EP_CANCEL_STEP) {
        ++f->cancel_steps;
        if (f->mode == HMS_FIXTURE_REJECT_CANCEL) r->cancellation = HMS_EP_CANCEL_REJECTED;
        else {
            r->cancellation = HMS_EP_CANCEL_ACK;
            if (f->mode == HMS_FIXTURE_COMPLETE_ON_CANCEL) complete(f, primitive, args, r);
            else { f->active = 0; r->terminal_state = HMS_EP_CANCELED; r->evidence_kind = HMS_EP_SIMULATION; }
        }
    } else if (phase == HMS_EP_RUN) {
        if (f->mode == HMS_FIXTURE_EARLY_QUIESCENCE) r->quiescent_mask = f->pending_quiescence;
        else if (f->mode != HMS_FIXTURE_NEVER_COMPLETE && now >= f->started && now - f->started >= 100u)
            complete(f, primitive, args, r);
    }
    f->clock_tick += f->step_advance_ms;
    if (f->mode == HMS_FIXTURE_LATE_CALLBACK && phase == HMS_EP_RUN && r->terminal_state == HMS_EP_COMPLETED)
        f->clock_tick += 20u;
}
void hms_endpoint_fixture_init(hms_endpoint_fixture *f, hms_ep_config *c) {
    memset(f, 0, sizeof(*f)); memset(c, 0, sizeof(*c));
#ifndef __AVR__
    memcpy(f->constants, constants, sizeof(constants));
#endif
    c->user = f; c->constant_byte = constant_byte; c->describe = describe;
    c->guard = guard; c->sample_clock = sample_clock; c->step = step; c->max_lease_ms = 60000; c->resource_count = 8;
    f->clock_tick = 1000; f->platform_flags = HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY;
}
#ifndef __AVR__
static uint8_t hex_digit(char c) {
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
    return 255;
}
uint8_t hms_endpoint_fixture_constant(hms_endpoint_fixture *f, uint8_t which, const char *hex) {
    uint8_t size = which == HMS_EP_INCARNATION ? 16u : 32u;
    uint8_t offset = which == HMS_EP_INCARNATION ? 0u : (which == HMS_EP_FIRMWARE ? 16u : 48u), i;
    if (strlen(hex) != (size_t)size * 2u) return 0;
    for (i = 0; i < size; ++i) if (hex_digit(hex[2u*i]) > 15u || hex_digit(hex[2u*i+1u]) > 15u) return 0;
    for (i = 0; i < size; ++i) f->constants[offset+i] = (uint8_t)((hex_digit(hex[2u*i]) << 4) | hex_digit(hex[2u*i+1u]));
    return 1;
}
#endif
