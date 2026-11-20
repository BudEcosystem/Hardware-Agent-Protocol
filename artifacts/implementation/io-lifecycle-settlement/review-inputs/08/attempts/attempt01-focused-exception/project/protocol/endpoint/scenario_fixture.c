#include "scenario_fixture.h"
#include <string.h>

/* Identity and label digest are synthetic; manifest digest is SHA256 of the
 * exact canonical scenario-manifest.json bytes, verified by the build check. */
static const uint8_t constants[80] = {
    0x7a,0x40,0x2b,0x2a,0xce,0xd8,0xa9,0x7c,0x6b,0x77,0x26,0x13,0x21,0xdf,0xf0,0x98,
    0x04,0x08,0x90,0x73,0x0a,0xf3,0x25,0x3f,0x71,0x1b,0xdb,0xb3,0x65,0x42,0xaf,0xc6,
    0x8f,0x28,0xb7,0x33,0xab,0x7a,0xe8,0xa3,0x33,0x04,0x66,0xc4,0x83,0x15,0x65,0x46,
    0xf8,0x2d,0xb3,0xe3,0x06,0x6e,0x98,0x7b,0x7d,0xbb,0x70,0x23,0x96,0xa4,0x34,0xd0,
    0x0c,0xd1,0xa7,0xce,0xc5,0xaf,0x29,0xf2,0x5a,0x17,0x79,0x1f,0xc2,0x21,0x9c,0x4e
};
static uint8_t constant_byte(void *user, uint8_t which, uint8_t index) {
    uint8_t offset = which == HMS_EP_INCARNATION ? 0u : (which == HMS_EP_FIRMWARE ? 16u : 48u);
    return ((hms_scenario_fixture *)user)->constants[offset + index];
}
/* Length-delimited UTF-8 accepts all Unicode scalar values, including U+0000;
 * it never treats the identifier as a C string. Reject overlongs/surrogates. */
static uint8_t valid_utf8(const uint8_t *p, uint8_t length) {
    uint8_t at = 0;
    while (at < length) {
        uint8_t first = p[at++], need, i;
        uint32_t value, minimum;
        if (first < 0x80u) continue;
        if (first >= 0xc2u && first <= 0xdfu) { need = 1; value = first & 0x1fu; minimum = 0x80u; }
        else if (first >= 0xe0u && first <= 0xefu) { need = 2; value = first & 0x0fu; minimum = 0x800u; }
        else if (first >= 0xf0u && first <= 0xf4u) { need = 3; value = first & 0x07u; minimum = 0x10000u; }
        else return 0;
        if ((uint16_t)at + need > length) return 0;
        for (i = 0; i < need; ++i) {
            uint8_t next = p[at++];
            if ((next & 0xc0u) != 0x80u) return 0;
            value = (value << 6) | (uint32_t)(next & 0x3fu);
        }
        if (value < minimum || value > 0x10ffffu || (value >= 0xd800u && value <= 0xdfffu)) return 0;
    }
    return 1;
}
static uint8_t index_for(uint16_t primitive) { return (uint8_t)(primitive - 0x1001u); }
static uint8_t describe(void *user, uint16_t primitive, const uint8_t *args,
                        uint8_t length, hms_ep_primitive *d) {
    (void)user;
    if (primitive == 0x1001u || primitive == 0x1002u) {
        if (length != 1u || args[0] > 100u) return HMS_EP_BAD_ARGUMENT;
    } else if (primitive == 0x1003u) {
        if (length < 3u || length > 66u || (args[0] != 1u && args[0] != 2u) ||
                args[1] < 1u || args[1] > 64u || length != (uint8_t)(args[1] + 2u) ||
                valid_utf8(args + 2, args[1]) == 0u) return HMS_EP_BAD_ARGUMENT;
    } else return HMS_EP_UNKNOWN_PRIMITIVE;
    d->max_run_ms = 5000; d->resource_mask = (uint8_t)(1u << index_for(primitive));
    d->cancel_supported = 1; d->result_length = 12;
    d->completion_evidence_mask = (uint8_t)(1u << HMS_EP_SIMULATION);
    return HMS_EP_OK;
}
static uint8_t guard(void *user, uint16_t primitive, const uint8_t *args, uint8_t length) {
    hms_scenario_fixture *f = user;
    (void)args; (void)length;
    if (f->guard_denied != 0u || (primitive == 0x1003u && f->values[2] >= 1000000u)) return HMS_EP_BAD_STATE;
    return HMS_EP_OK;
}
static uint8_t sample_clock(void *user, uint64_t *tick, uint16_t *flags) {
    hms_scenario_fixture *f = user;
    if (f->clock_snapshot != NULL) return f->clock_snapshot(user, tick, flags);
    *tick = f->clock_tick; *flags = f->platform_flags; return 1;
}
static void result(hms_ep_report *r, uint64_t tick, uint32_t value) {
    uint8_t i;
    r->result_length = 12;
    for (i = 0; i < 8u; ++i) { r->result[7u-i] = (uint8_t)tick; tick >>= 8; }
    for (i = 0; i < 4u; ++i) { r->result[11u-i] = (uint8_t)value; value >>= 8; }
}
static uint8_t current(hms_scenario_fixture *f, uint64_t entry,
                        const hms_ep_step_limits *limits, uint64_t *tick) {
    uint16_t flags;
    if (sample_clock(f, tick, &flags) == 0u || *tick < entry || *tick == UINT64_MAX ||
            *tick >= limits->ordinary_until ||
            (flags & (HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY)) !=
                (HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY) ||
            (flags & (HMS_EP_RECONCILE | HMS_EP_PHYSICAL_COMMISSIONED)) != 0u) return 0;
    return 1;
}
static void complete(hms_scenario_fixture *f, uint16_t primitive, const uint8_t *args,
                      uint64_t tick, hms_ep_report *r) {
    uint8_t index = index_for(primitive);
    /* Recheck at the actual synthetic commit; guard alone is not a reservation. */
    if (f->effects == UINT32_MAX || (index == 2u && f->values[index] >= 1000000u)) {
        r->terminal_state = HMS_EP_FAILED; r->evidence_kind = HMS_EP_SIMULATION; f->active = 0; return;
    }
    f->values[index] = index == 2u ? f->values[index] + 1u : args[0];
    f->sample_ticks[index] = tick; ++f->effects; f->active = 0;
    r->terminal_state = HMS_EP_COMPLETED; r->evidence_kind = HMS_EP_SIMULATION;
    result(r, tick, f->values[index]);
    if (f->mode == HMS_SCENARIO_FALSE_PHYSICAL) { r->evidence_kind = HMS_EP_PHYSICAL_SENSOR; r->verification = HMS_EP_VERIFIED; }
    if (f->mode == HMS_SCENARIO_OVERSIZE_RESULT) r->result_length = 33;
}
static void step(void *user, uint8_t phase, uint16_t primitive, const uint8_t *args,
                 uint8_t length, uint64_t now, const hms_ep_step_limits *limits, hms_ep_report *r) {
    hms_scenario_fixture *f = user;
    uint64_t tick = now;
    (void)length;
    if (phase == HMS_EP_QUIESCENCE_STEP) {
        if (f->mode != HMS_SCENARIO_NO_QUIESCENCE) { r->quiescent_mask = f->pending_quiescence; f->pending_quiescence = 0; }
    } else if (phase == HMS_EP_LOSS_STEP) {
        if (f->loss_steps < UINT32_MAX) ++f->loss_steps;
        f->active = 0; r->terminal_state = HMS_EP_FAILED; r->evidence_kind = HMS_EP_SIMULATION;
    } else if (phase == HMS_EP_CANCEL_STEP) {
        if (f->cancel_steps < UINT32_MAX) ++f->cancel_steps;
        if (f->mode == HMS_SCENARIO_REJECT_CANCEL) r->cancellation = HMS_EP_CANCEL_REJECTED;
        else {
            r->cancellation = HMS_EP_CANCEL_ACK;
            if (f->mode == HMS_SCENARIO_COMPLETE_ON_CANCEL && current(f, now, limits, &tick) != 0u)
                complete(f, primitive, args, tick, r);
            else { f->active = 0; r->terminal_state = HMS_EP_CANCELED; r->evidence_kind = HMS_EP_SIMULATION; }
        }
    } else if (phase == HMS_EP_START) {
        f->pending_quiescence = (uint8_t)(1u << index_for(primitive));
        if (current(f, now, limits, &tick) == 0u || tick >= limits->latest_start || f->dispatches == UINT32_MAX) {
            r->terminal_state = HMS_EP_FAILED; r->evidence_kind = HMS_EP_SIMULATION; return;
        }
        ++f->dispatches; f->active = 1; f->started = tick;
    } else if (phase == HMS_EP_RUN) {
        if (f->mode == HMS_SCENARIO_EARLY_QUIESCENCE) r->quiescent_mask = f->pending_quiescence;
        else if (f->mode != HMS_SCENARIO_NEVER_COMPLETE && current(f, now, limits, &tick) != 0u &&
                 tick >= f->started && tick - f->started >= 100u) {
            complete(f, primitive, args, tick, r);
            /* Explicit fault-injection mode: commit, then callback stalls. */
            if (f->mode == HMS_SCENARIO_LATE_CALLBACK) {
                if (f->clock_tick <= UINT64_MAX - 20u) f->clock_tick += 20u;
                else f->platform_flags = (uint16_t)(f->platform_flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);
            }
        }
    }
}
void hms_scenario_fixture_init(hms_scenario_fixture *f, hms_ep_config *c) {
    memset(f, 0, sizeof(*f)); memset(c, 0, sizeof(*c));
    memcpy(f->constants, constants, sizeof(constants));
    c->user = f; c->constant_byte = constant_byte; c->describe = describe;
    c->guard = guard; c->sample_clock = sample_clock; c->step = step;
    c->max_lease_ms = 60000; c->resource_count = 3;
    f->clock_tick = 1000; f->platform_flags = HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY;
}
static uint8_t hex_digit(char c) {
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
    return 255;
}
uint8_t hms_scenario_fixture_constant(hms_scenario_fixture *f, uint8_t which, const char *hex) {
    uint8_t size = which == HMS_EP_INCARNATION ? 16u : 32u;
    uint8_t offset = which == HMS_EP_INCARNATION ? 0u : (which == HMS_EP_FIRMWARE ? 16u : 48u), i;
    if (which > HMS_EP_MANIFEST || strlen(hex) != (size_t)size * 2u) return 0;
    for (i = 0; i < size; ++i) if (hex_digit(hex[2u*i]) > 15u || hex_digit(hex[2u*i+1u]) > 15u) return 0;
    for (i = 0; i < size; ++i) f->constants[offset+i] = (uint8_t)((hex_digit(hex[2u*i]) << 4) | hex_digit(hex[2u*i+1u]));
    return 1;
}
