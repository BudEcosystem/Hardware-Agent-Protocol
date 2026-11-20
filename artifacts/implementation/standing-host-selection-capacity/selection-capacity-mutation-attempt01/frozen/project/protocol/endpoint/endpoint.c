#include "endpoint.h"
#include "standing.h"

#include <string.h>

#define OP_HELLO 1u
#define OP_BIND 16u
#define OP_ARM 17u
#define OP_REVOKE 18u
#define OP_CALL 32u
#define OP_QUERY 33u
#define OP_CANCEL 34u
#define OP_RETIRE 35u
#define PLATFORM_BITS 95u /* Caller cannot supply the derived INHIBITED bit. */

static uint16_t get16(const uint8_t *p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}
static uint32_t get32(const uint8_t *p) {
    uint32_t v = 0; uint8_t i;
    for (i = 0; i < 4u; ++i) v = (v << 8) | p[i];
    return v;
}
static uint64_t get64(const uint8_t *p) {
    uint64_t v = 0; uint8_t i;
    for (i = 0; i < 8u; ++i) v = (v << 8) | p[i];
    return v;
}
static void put16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v;
}
static void put32(uint8_t *p, uint32_t v) {
    uint8_t i;
    for (i = 0; i < 4u; ++i) { p[3u - i] = (uint8_t)v; v >>= 8; }
}
static void put64(uint8_t *p, uint64_t v) {
    uint8_t i;
    for (i = 0; i < 8u; ++i) { p[7u - i] = (uint8_t)v; v >>= 8; }
}
static uint8_t bits(uint8_t v) {
    uint8_t n = 0;
    while (v != 0u) { n = (uint8_t)(n + (v & 1u)); v >>= 1; }
    return n;
}
static uint8_t nonzero(const uint8_t *p, uint8_t length) {
    uint8_t v = 0, i;
    for (i = 0; i < length; ++i) v |= p[i];
    return (uint8_t)(v != 0u);
}
static uint8_t terminal(uint8_t state) {
    return (uint8_t)(state >= HMS_EP_COMPLETED && state <= HMS_EP_REJECTED);
}
static uint8_t eligible(const hms_endpoint *e) {
    return (uint8_t)((e->flags & (HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED)) ==
                    (HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED) &&
                    (e->flags & HMS_EP_RECONCILE) == 0u &&
                    (e->flags & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY)) != 0u);
}
static void inhibit_flag(hms_endpoint *e) {
    e->flags = (uint16_t)(e->flags & (uint16_t)~HMS_EP_INHIBITED);
    if (e->state != HMS_EP_ARMED || e->context_valid == 0u || eligible(e) == 0u)
        e->flags |= HMS_EP_INHIBITED;
}
static void fault(hms_endpoint *e, uint8_t reason) {
    e->state = HMS_EP_FAULT; e->context_valid = 0; e->armed_until = 0;
    if (e->loss_reason == 0u || reason == 7u) e->loss_reason = reason;
    e->flags |= HMS_EP_INHIBITED;
}
static uint8_t revision(hms_endpoint *e) {
    if (e->receipt.revision == UINT32_MAX) { fault(e, 12); return 0; }
    ++e->receipt.revision;
    return 1;
}
static void reject_queued(hms_endpoint *e, uint8_t reason, uint8_t canceled) {
    if (e->receipt.execution != HMS_EP_QUEUED || revision(e) == 0u) return;
    e->receipt.execution = canceled != 0u ? HMS_EP_CANCELED : HMS_EP_REJECTED;
    e->receipt.cancellation = canceled != 0u ? HMS_EP_CANCEL_CONFIRMED : HMS_EP_CANCEL_NONE;
    e->receipt.held_mask = 0; e->receipt.reason = reason;
    e->receipt.terminal_at = (e->flags & HMS_EP_CLOCK_QUALIFIED) != 0u ? e->now_tick : HMS_EP_TIME_ABSENT;
}
static void drain_state(hms_endpoint *e) {
    if (e->state == HMS_EP_FAULT) { e->flags |= HMS_EP_INHIBITED; return; }
    if (e->state == HMS_EP_DRAINING &&
            (e->operation_length == 0u || (terminal(e->receipt.execution) != 0u && e->receipt.held_mask == 0u))) {
        e->state = e->context_valid != 0u ? HMS_EP_BOUND : HMS_EP_RESET;
    }
    inhibit_flag(e);
}
static void invalidate(hms_endpoint *e, uint8_t reason) {
    e->context_valid = 0; e->armed_until = 0;
    if (e->control_generation == UINT32_MAX) fault(e, 12);
    else { ++e->control_generation; e->state = HMS_EP_RESET; }
    reject_queued(e, reason, 0);
    if (e->operation_length != 0u && terminal(e->receipt.execution) == 0u) {
        e->loss_reason = reason;
        if (e->state != HMS_EP_FAULT) e->state = HMS_EP_DRAINING;
    } else if (e->receipt.held_mask != 0u && e->state != HMS_EP_FAULT) {
        e->state = HMS_EP_DRAINING;
    }
    inhibit_flag(e);
}

/* Eligibility/expiry bookkeeping only: never calls a primitive. */
static void update(hms_endpoint *e, uint64_t now, uint16_t supplied) {
    uint16_t flags = (uint16_t)(supplied & PLATFORM_BITS);
    uint16_t previous_mode = (uint16_t)(e->flags & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY));
    uint8_t was_context = e->context_valid;
    if ((e->flags & HMS_EP_BOOT_QUALIFIED) == 0u) flags = (uint16_t)(flags & (uint16_t)~HMS_EP_BOOT_QUALIFIED);
    if ((supplied & (uint16_t)~127u) != 0u ||
            (flags & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY)) ==
            (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY)) {
        flags = (uint16_t)(flags & (uint16_t)~HMS_EP_PHYSICAL_COMMISSIONED);
        fault(e, 10);
    }
    if ((flags & HMS_EP_CLOCK_QUALIFIED) == 0u || now < e->now_tick || now == HMS_EP_TIME_ABSENT) {
        flags = (uint16_t)(flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);
        fault(e, 7);
    } else if (e->state != HMS_EP_FAULT || (e->flags & HMS_EP_CLOCK_QUALIFIED) != 0u) {
        e->now_tick = now;
    }
    /* A clock fault is latched; a later optimistic platform flag cannot repair it. */
    if (e->state == HMS_EP_FAULT && (e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u)
        flags = (uint16_t)(flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);
    e->flags = flags;
    if ((flags & HMS_EP_BOOT_QUALIFIED) == 0u) fault(e, 11);
    if (was_context != 0u && e->state != HMS_EP_FAULT &&
            (eligible(e) == 0u || previous_mode != (flags & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY))))
        invalidate(e, (flags & HMS_EP_RECONCILE) != 0u ? 11u : 10u);
    if (e->state == HMS_EP_FAULT) reject_queued(e, e->loss_reason, 0);
    if (e->state == HMS_EP_ARMED && e->now_tick >= e->armed_until) {
        e->armed_until = 0; e->state = HMS_EP_BOUND;
        reject_queued(e, 4, 0);
        if (e->operation_length != 0u && terminal(e->receipt.execution) == 0u) {
            e->loss_reason = 4; e->state = HMS_EP_DRAINING;
        } else if (e->receipt.held_mask != 0u) e->state = HMS_EP_DRAINING;
    }
    if (e->receipt.execution == HMS_EP_QUEUED && e->now_tick >= get64(e->operation + 60))
        reject_queued(e, 1, 0);
    drain_state(e);
}

static void sample_clock(hms_endpoint *e) {
    uint64_t tick = e->now_tick;
    uint16_t flags = (uint16_t)(e->flags & PLATFORM_BITS);
    uint8_t valid;
    e->callback_active = 1;
    valid = e->config->sample_clock(e->config->user, &tick, &flags);
    e->callback_active = 0;
    if (valid == 0u) flags = (uint16_t)(flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);
    update(e, tick, flags);
}
static uint8_t guard_call(hms_endpoint *e, const uint8_t *p) {
    uint8_t status;
    e->callback_active = 1;
    status = e->config->guard(e->config->user, get16(p + 44), p + 88u + (uint16_t)bits(p[46]) * 4u, p[47]);
    e->callback_active = 0;
    return status;
}

uint8_t hms_endpoint_init(hms_endpoint *e, const hms_ep_config *c,
                          uint64_t boot, uint64_t now, uint16_t flags) {
    memset(e, 0, sizeof(*e));
    e->config = c; e->control_generation = 1; e->state = HMS_EP_RESET;
    e->receipt.started_at = e->receipt.terminal_at = HMS_EP_TIME_ABSENT;
    if (c == NULL || c->constant_byte == NULL || c->describe == NULL ||
            c->guard == NULL || c->sample_clock == NULL || c->step == NULL || c->resource_count == 0u ||
            c->resource_count > 8u || c->max_lease_ms == 0u || c->max_lease_ms > 60000u) {
        e->config = NULL; fault(e, 10); return 0;
    }
    e->flags = (uint16_t)(flags & PLATFORM_BITS);
    if (boot == 0u || (flags & HMS_EP_BOOT_QUALIFIED) == 0u) {
        e->flags = (uint16_t)(e->flags & (uint16_t)~HMS_EP_BOOT_QUALIFIED);
        e->boot_epoch = 0;
    } else e->boot_epoch = boot;
    e->now_tick = now == HMS_EP_TIME_ABSENT ? 0 : now;
    update(e, now, flags);
    return 1;
}

static uint8_t same_constant(hms_endpoint *e, uint8_t which, const uint8_t *p, uint8_t n) {
    uint8_t i, equal = 1;
    e->callback_active = 1;
    for (i = 0; i < n; ++i)
        if (e->config->constant_byte(e->config->user, which, i) != p[i]) equal = 0;
    e->callback_active = 0;
    return equal;
}
static void constant_copy(hms_endpoint *e, uint8_t which, uint8_t *p, uint8_t n) {
    uint8_t i;
    e->callback_active = 1;
    for (i = 0; i < n; ++i) p[i] = e->config->constant_byte(e->config->user, which, i);
    e->callback_active = 0;
}
static uint8_t context_matches(const hms_endpoint *e, const uint8_t *p) {
    return (uint8_t)(get32(p + 2) == e->control_generation && get16(p + 6) == e->context_handle);
}
static uint8_t readiness(const hms_endpoint *e) {
    if ((e->flags & HMS_EP_RECONCILE) != 0u) return HMS_EP_RECONCILIATION_REQUIRED;
    if ((e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u) return HMS_EP_CLOCK_UNQUALIFIED;
    if ((e->flags & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_SIMULATOR_ONLY)) == 0u) return HMS_EP_UNCOMMISSIONED;
    return HMS_EP_OK;
}
static uint8_t reference(const hms_endpoint *e, const uint8_t *p) {
    uint32_t call = get32(p + 8);
    if (e->operation_length == 0u || get32(e->operation + 8) != call)
        return call <= e->call_high_water ? HMS_EP_OLD_OR_FORGOTTEN : HMS_EP_NOT_SEEN;
    if (memcmp(e->operation + 2, p + 2, 10u) != 0 || memcmp(e->operation + 12, p + 12, 32u) != 0)
        return HMS_EP_CONFLICT;
    return HMS_EP_OK;
}
static uint8_t syntax(const uint8_t *p, uint16_t length) {
    uint16_t expected;
    if (p[0] != 1u) return HMS_EP_UNSUPPORTED;
    switch (p[1]) {
        case OP_HELLO: expected = 2; break;
        case OP_BIND: expected = 72; break;
        case OP_ARM: expected = 48; break;
        case OP_REVOKE: expected = 10; break;
        case OP_QUERY: case OP_CANCEL: case OP_RETIRE: expected = 44; break;
        case OP_CALL:
            if (length < 88u || p[47] > HMS_EP_ARGUMENTS) return HMS_EP_BAD_LENGTH;
            expected = (uint16_t)(88u + (uint16_t)bits(p[46]) * 4u + p[47]);
            if (p[49] != 0u || get16(p + 50) != 0u) return HMS_EP_RESERVED;
            if (p[48] > 1u) return HMS_EP_UNSUPPORTED;
            if (get16(p + 44) == 0u) return HMS_EP_UNKNOWN_PRIMITIVE;
            break;
        default: return HMS_EP_UNSUPPORTED;
    }
    if (length != expected) return HMS_EP_BAD_LENGTH;
    if (p[1] != OP_HELLO && (get32(p + 2) == 0u || get16(p + 6) == 0u)) return HMS_EP_BAD_ARGUMENT;
    if (p[1] >= OP_CALL && get32(p + 8) == 0u) return HMS_EP_BAD_ARGUMENT;
    return HMS_EP_OK;
}
static uint8_t known_opcode(uint8_t op) {
    return (uint8_t)(op == OP_HELLO || op == OP_BIND || op == OP_ARM || op == OP_REVOKE ||
                    op == OP_CALL || op == OP_QUERY || op == OP_CANCEL || op == OP_RETIRE);
}
static uint8_t bind_context(hms_endpoint *e, const uint8_t *p) {
    uint8_t ready = readiness(e);
    if (ready != 0u) return ready;
    if (e->state != HMS_EP_RESET && e->state != HMS_EP_BOUND) return HMS_EP_BAD_STATE;
    if (get32(p + 2) != e->control_generation) return HMS_EP_CONTEXT_MISMATCH;
    if (e->operation_length != 0u || e->receipt.held_mask != 0u) return HMS_EP_BUSY;
    if (get16(p + 6) <= e->context_handle || nonzero(p + 8, 32) == 0u || nonzero(p + 40, 32) == 0u)
        return HMS_EP_BAD_ARGUMENT;
    if (same_constant(e, HMS_EP_MANIFEST, p + 8, 32) == 0u) return HMS_EP_CONTEXT_MISMATCH;
    if (e->control_generation == UINT32_MAX) { fault(e, 12); return HMS_EP_COUNTER_EXHAUSTED; }
    ++e->control_generation; e->context_handle = get16(p + 6);
    memcpy(e->context_digest, p + 40, 32); e->context_valid = 1;
    e->state = HMS_EP_BOUND; e->armed_until = 0; e->loss_reason = 0;
    inhibit_flag(e);
    return HMS_EP_OK;
}
static uint8_t arm_context(hms_endpoint *e, const uint8_t *p) {
    uint8_t ready = readiness(e);
    uint64_t until = get64(p + 40);
    if (ready != 0u) return ready;
    if (context_matches(e, p) == 0u || memcmp(e->context_digest, p + 8, 32) != 0) return HMS_EP_CONTEXT_MISMATCH;
    if (e->context_valid == 0u || (e->state != HMS_EP_BOUND && e->state != HMS_EP_ARMED)) return HMS_EP_BAD_STATE;
    if (until == HMS_EP_TIME_ABSENT || until <= e->now_tick || until - e->now_tick > e->config->max_lease_ms)
        return HMS_EP_LEASE_INVALID;
    if (until > e->armed_until) e->armed_until = until;
    e->state = HMS_EP_ARMED; inhibit_flag(e);
    return HMS_EP_OK;
}
static const uint8_t *arguments(const uint8_t *p) {
    return p + 88u + (uint16_t)bits(p[46]) * 4u;
}
static uint8_t admit(hms_endpoint *e, const uint8_t *p, uint16_t length) {
    uint32_t call = get32(p + 8), run = get32(p + 76);
    uint64_t nb = get64(p + 52), latest = get64(p + 60), complete = get64(p + 68), lease = get64(p + 80);
    uint8_t i, index = 0, status;
    hms_ep_primitive description;
    if (e->operation_length != 0u && call == get32(e->operation + 8)) {
        if (e->operation_length != length || memcmp(e->operation, p, length) != 0) return HMS_EP_CONFLICT;
        return HMS_EP_OK;
    }
    if (call <= e->call_high_water) return HMS_EP_OLD_OR_FORGOTTEN;
    if (context_matches(e, p) == 0u) return HMS_EP_CONTEXT_MISMATCH;
    status = readiness(e); if (status != 0u) return status;
    if (e->state != HMS_EP_ARMED || e->context_valid == 0u) return HMS_EP_BAD_STATE;
    if (e->operation_length != 0u || e->receipt.held_mask != 0u) return HMS_EP_BUSY;
    memset(&description, 0, sizeof(description));
    e->callback_active = 1;
    status = e->config->describe(e->config->user, get16(p + 44), arguments(p), p[47], &description);
    e->callback_active = 0;
    if (status != 0u) return status <= HMS_EP_RECONCILIATION_REQUIRED ? status : HMS_EP_BAD_ARGUMENT;
    if (description.resource_mask == 0u || description.max_run_ms == 0u ||
            description.max_run_ms > UINT32_C(0x7fffffff) || description.cancel_supported > 1u || description.result_length > 32u ||
            description.completion_evidence_mask == 0u || (description.completion_evidence_mask & 0xc1u) != 0u)
        return HMS_EP_BAD_ARGUMENT;
    if (p[46] != description.resource_mask ||
            (uint16_t)p[46] >= ((uint16_t)1u << e->config->resource_count)) return HMS_EP_RESOURCE_MISMATCH;
    if (p[48] != 0u && ((e->flags & HMS_EP_PHYSICAL_COMMISSIONED) == 0u ||
            (description.completion_evidence_mask & ((1u << HMS_EP_CONTROLLER_MEASUREMENT) | (1u << HMS_EP_PHYSICAL_SENSOR))) == 0u))
        return HMS_EP_UNCOMMISSIONED;
    if (run == 0u || run > description.max_run_ms || nb >= latest || latest > complete ||
            complete == HMS_EP_TIME_ABSENT || lease == HMS_EP_TIME_ABSENT) return HMS_EP_BAD_TIME;
    if (e->now_tick >= latest) return HMS_EP_START_EXPIRED;
    if ((nb > e->now_tick && nb - e->now_tick > UINT32_C(0x7fffffff)) ||
            latest - e->now_tick > UINT32_C(0x7fffffff) || complete - e->now_tick > UINT32_C(0x7fffffff))
        return HMS_EP_BAD_TIME;
    if (complete > lease || lease > e->armed_until || lease <= e->now_tick) return HMS_EP_LEASE_INVALID;
    for (i = 0; i < 8u; ++i) if ((p[46] & ((uint8_t)1u << i)) != 0u) {
        uint32_t fence = get32(p + 88u + (uint16_t)index * 4u);
        if (fence == 0u || fence <= e->fence_floor[i]) return HMS_EP_STALE_FENCE;
        ++index;
    }
    status = guard_call(e, p);
    if (status != 0u) return status <= HMS_EP_RECONCILIATION_REQUIRED ? status : HMS_EP_BAD_ARGUMENT;
    sample_clock(e);
    status = readiness(e); if (status != 0u) return status;
    if (e->state != HMS_EP_ARMED || e->context_valid == 0u) return HMS_EP_BAD_STATE;
    if (context_matches(e, p) == 0u) return HMS_EP_CONTEXT_MISMATCH;
    if (e->now_tick >= latest) return HMS_EP_START_EXPIRED;
    if (e->now_tick >= lease || lease > e->armed_until) return HMS_EP_LEASE_INVALID;
    /* All validation finished. One serialized owner commits every local claim
     * before a driver can be called; callbacks cannot observe a partial grant. */
    memcpy(e->operation, p, length); e->operation_length = (uint8_t)length;
    e->call_high_water = call; index = 0;
    for (i = 0; i < 8u; ++i) if ((p[46] & ((uint8_t)1u << i)) != 0u) {
        e->fence_floor[i] = get32(p + 88u + (uint16_t)index * 4u); ++index;
    }
    memset(&e->receipt, 0, sizeof(e->receipt));
    e->receipt.execution = HMS_EP_QUEUED; e->receipt.held_mask = p[46];
    e->receipt.revision = 1; e->receipt.queued_at = e->now_tick;
    e->receipt.started_at = e->receipt.terminal_at = HMS_EP_TIME_ABSENT;
    e->completion_evidence_mask = description.completion_evidence_mask;
    e->cancel_supported = description.cancel_supported; e->result_length = description.result_length; e->loss_reason = 0;
    e->operation_simulator_only = (uint8_t)((e->flags & HMS_EP_SIMULATOR_ONLY) != 0u);
    if (e->standing != NULL) hms_standing_finite_slot(e->standing, 1);
    return HMS_EP_OK;
}

static uint16_t write_hello(hms_endpoint *e, uint8_t *p) {
    uint8_t i;
    constant_copy(e, HMS_EP_INCARNATION, p + 7, 16);
    constant_copy(e, HMS_EP_FIRMWARE, p + 23, 32);
    constant_copy(e, HMS_EP_MANIFEST, p + 55, 32);
    put32(p + 87, e->control_generation); put16(p + 91, e->context_handle);
    memcpy(p + 93, e->context_digest, 32); p[125] = e->state; put16(p + 126, e->flags);
    p[128] = e->config->resource_count; p[129] = 72; p[130] = 32; p[131] = p[132] = 1;
    put64(p + 133, e->now_tick); put64(p + 141, e->armed_until); put32(p + 149, e->call_high_water);
    p[153] = e->receipt.held_mask;
    for (i = 0; i < 8u; ++i) put32(p + 154u + (uint16_t)i * 4u, e->fence_floor[i]);
    return 186;
}
static uint16_t write_control(const hms_endpoint *e, uint8_t *p) {
    put32(p + 7, e->control_generation); put16(p + 11, e->context_handle);
    memcpy(p + 13, e->context_digest, 32); p[45] = e->state; put16(p + 46, e->flags);
    put64(p + 48, e->now_tick); put64(p + 56, e->armed_until); put32(p + 64, e->call_high_water);
    p[68] = e->receipt.held_mask;
    return 69;
}
static uint16_t write_receipt(const hms_endpoint *e, uint8_t *p) {
    const hms_ep_receipt *r = &e->receipt;
    memcpy(p + 7, e->operation + 2, 42);
    p[49] = r->execution; p[50] = r->cancellation; p[51] = r->evidence_kind;
    p[52] = r->verification; p[53] = r->held_mask; p[54] = r->may_have_acted;
    put16(p + 55, r->reason); put32(p + 57, r->revision);
    put64(p + 61, r->queued_at); put64(p + 69, r->started_at); put64(p + 77, r->terminal_at);
    p[85] = r->result_length; memcpy(p + 86, r->result, r->result_length);
    return (uint16_t)(86u + r->result_length);
}

uint8_t hms_endpoint_handle(hms_endpoint *e, uint8_t kind, uint8_t channel,
                            uint64_t session, uint32_t sequence,
                            const uint8_t *p, uint16_t length,
                            uint64_t now, uint16_t flags,
                            uint8_t *out, uint16_t *out_length) {
    uint8_t status, op;
    if (out_length != NULL) *out_length = 0;
    if (e != NULL && e->config != NULL && e->callback_active == 0u &&
            e->standing != NULL && p != NULL && length >= 2u &&
            length <= HMS_EP_PAYLOAD && p[0] == 2u)
        return hms_standing_handle(e->standing, kind, channel, session, sequence,
                                   p, length, now, flags, out, out_length);
    if (e == NULL || e->config == NULL || e->callback_active != 0u || p == NULL || length < 2u || length > 192u || known_opcode(p[1]) == 0u) return 0;
    update(e, now, flags); op = p[1];
    status = syntax(p, length);
    /* No v1 snapshot/query/control can mistake OPEN bytes for a finite OP or
     * expose a standing owner as an empty slot. This is the common public API,
     * not merely a transport/host-side convention. */
    if (e->standing != NULL && e->standing->bytes[ST_SLOT] == ST_STANDING)
        status = HMS_EP_UNSUPPORTED;
    if (status == 0u && (kind != 1u || channel != 0u)) status = HMS_EP_UNSUPPORTED;
    if (status == 0u && op == OP_HELLO && session != 0u) status = HMS_EP_BOOT_MISMATCH;
    if (status == 0u && op != OP_HELLO) {
        if ((e->flags & HMS_EP_BOOT_QUALIFIED) == 0u) status = HMS_EP_BOOT_UNQUALIFIED;
        else if (session != e->boot_epoch) status = HMS_EP_BOOT_MISMATCH;
        else if (sequence == 0u) status = HMS_EP_BAD_ARGUMENT;
    }
    if (e->response_sequence == UINT32_MAX) {
        fault(e, 12);
        if (op != OP_CANCEL && op != OP_REVOKE) return 0;
    }
    if (status == 0u) switch (op) {
        case OP_HELLO: break;
        case OP_BIND: status = bind_context(e, p); break;
        case OP_ARM: status = arm_context(e, p); break;
        case OP_REVOKE:
            if (get16(p + 8) != 6u) status = HMS_EP_RESERVED;
            else if (context_matches(e, p) == 0u) status = HMS_EP_CONTEXT_MISMATCH;
            else if (e->context_valid == 0u || (e->state != HMS_EP_BOUND && e->state != HMS_EP_ARMED)) status = HMS_EP_BAD_STATE;
            else { invalidate(e, 6); if (e->state == HMS_EP_FAULT) status = HMS_EP_COUNTER_EXHAUSTED; }
            break;
        case OP_CALL: status = admit(e, p, length); break;
        case OP_QUERY: status = reference(e, p); break;
        case OP_CANCEL:
            status = reference(e, p);
            if (status == 0u && e->receipt.execution == HMS_EP_QUEUED) reject_queued(e, 5, 1);
            else if (status == 0u && terminal(e->receipt.execution) == 0u && e->receipt.cancellation == HMS_EP_CANCEL_NONE) {
                if (revision(e) != 0u) e->receipt.cancellation = e->cancel_supported != 0u ? HMS_EP_CANCEL_REQUESTED : HMS_EP_CANCEL_REJECTED;
            }
            break;
        case OP_RETIRE:
            status = reference(e, p);
            if (status == 0u && (terminal(e->receipt.execution) == 0u || e->receipt.held_mask != 0u || e->receipt.verification == HMS_EP_DISPUTED)) status = HMS_EP_BUSY;
            if (status == 0u) {
                e->operation_length = 0; memset(&e->receipt, 0, sizeof(e->receipt)); e->loss_reason = 0;
                if (e->standing != NULL) hms_standing_finite_slot(e->standing, 0);
                drain_state(e);
                if (e->call_high_water == UINT32_MAX) fault(e, 12);
            }
            break;
        default: status = HMS_EP_UNSUPPORTED; break;
    }
    inhibit_flag(e);
    if (e->response_sequence == UINT32_MAX) return 0;
    ++e->response_sequence;
    if (out == NULL) return 1;
    out[0] = 1; out[1] = (uint8_t)(op | 0x80u); put32(out + 2, sequence); out[6] = status;
    if (out_length != NULL) {
        *out_length = 7;
        if (status == 0u) {
            if (op == OP_HELLO) *out_length = write_hello(e, out);
            else if (op == OP_BIND || op == OP_ARM || op == OP_REVOKE) *out_length = write_control(e, out);
            else if (op != OP_RETIRE) *out_length = write_receipt(e, out);
        }
    }
    return 1;
}

static void unknown_report(hms_endpoint *e, uint8_t reason) {
    if ((e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u) reason = 7;
    if (revision(e) != 0u) {
        if (terminal(e->receipt.execution) != 0u) e->receipt.verification = HMS_EP_DISPUTED;
        else e->receipt.execution = HMS_EP_UNKNOWN;
        e->receipt.reason = reason;
    }
    fault(e, reason);
}
static void bad_report(hms_endpoint *e) { unknown_report(e, 8); }
static void apply_report(hms_endpoint *e, const hms_ep_report *r) {
    uint8_t was_terminal = terminal(e->receipt.execution), changed = 0;
    if (r->result_length > 32u || r->evidence_kind > HMS_EP_SIMULATION || r->verification > HMS_EP_DISPUTED ||
            (r->cancellation != 0u && r->cancellation != HMS_EP_CANCEL_ACK && r->cancellation != HMS_EP_CANCEL_REJECTED) ||
            (r->quiescent_mask & (uint8_t)~e->receipt.held_mask) != 0u ||
            (r->evidence_kind == HMS_EP_EVIDENCE_NONE && r->result_length != 0u) ||
            (r->result_length != 0u && r->result_length != e->result_length) ||
            (e->operation_simulator_only != 0u &&
             (r->evidence_kind == HMS_EP_CONTROLLER_MEASUREMENT || r->evidence_kind == HMS_EP_PHYSICAL_SENSOR)) ||
            (e->operation_simulator_only == 0u && r->evidence_kind == HMS_EP_SIMULATION)) { bad_report(e); return; }
    if (r->verification == HMS_EP_VERIFIED &&
            ((e->flags & HMS_EP_PHYSICAL_COMMISSIONED) == 0u ||
             (r->evidence_kind != HMS_EP_CONTROLLER_MEASUREMENT && r->evidence_kind != HMS_EP_PHYSICAL_SENSOR))) { bad_report(e); return; }
    if (r->terminal_state != 0u &&
            (was_terminal != 0u || (r->terminal_state != HMS_EP_COMPLETED && r->terminal_state != HMS_EP_FAILED && r->terminal_state != HMS_EP_CANCELED && r->terminal_state != HMS_EP_UNKNOWN))) { bad_report(e); return; }
    if (r->terminal_state == HMS_EP_COMPLETED &&
            (e->loss_reason != 0u || r->result_length != e->result_length ||
             (e->completion_evidence_mask & ((uint8_t)1u << r->evidence_kind)) == 0u ||
             (e->operation[48] != 0u && r->verification != HMS_EP_VERIFIED))) { bad_report(e); return; }
    if (r->terminal_state == HMS_EP_CANCELED && e->receipt.cancellation != HMS_EP_CANCEL_REQUESTED && e->receipt.cancellation != HMS_EP_CANCEL_ACK) { bad_report(e); return; }
    if (r->quiescent_mask != 0u && was_terminal == 0u && terminal(r->terminal_state) == 0u) { bad_report(e); return; }
    if (r->terminal_state == 0u && (r->result_length != 0u || r->evidence_kind != 0u || r->verification != 0u)) { bad_report(e); return; }
    if (r->cancellation != 0u && e->receipt.cancellation != HMS_EP_CANCEL_REQUESTED && e->receipt.cancellation != HMS_EP_CANCEL_ACK && e->receipt.cancellation != HMS_EP_CANCEL_REJECTED) { bad_report(e); return; }
    if (r->terminal_state != 0u || r->quiescent_mask != 0u ||
            (r->cancellation != 0u && r->cancellation != e->receipt.cancellation)) changed = 1;
    if (changed == 0u || revision(e) == 0u) return;
    if (r->cancellation != 0u) e->receipt.cancellation = r->cancellation;
    if (r->terminal_state != 0u) {
        e->receipt.execution = r->terminal_state; e->receipt.evidence_kind = r->evidence_kind;
        e->receipt.verification = r->verification; e->receipt.result_length = r->result_length;
        memcpy(e->receipt.result, r->result, r->result_length);
        if (terminal(r->terminal_state) != 0u)
            e->receipt.terminal_at = (e->flags & HMS_EP_CLOCK_QUALIFIED) != 0u ? e->now_tick : HMS_EP_TIME_ABSENT;
        if (e->loss_reason != 0u) e->receipt.reason = e->loss_reason;
        if (r->terminal_state == HMS_EP_CANCELED) {
            e->receipt.cancellation = HMS_EP_CANCEL_CONFIRMED;
            e->receipt.reason = (e->flags & HMS_EP_CLOCK_QUALIFIED) != 0u ? 5u : 7u;
        }
        if (r->terminal_state == HMS_EP_UNKNOWN) {
            if ((e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u) { e->loss_reason = 7; e->receipt.reason = 7; }
            else { if (e->loss_reason == 0u) e->loss_reason = 8; e->receipt.reason = 9; }
        }
        if (terminal(r->terminal_state) != 0u && (e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u)
            e->receipt.reason = 7;
    }
    if (e->receipt.verification == HMS_EP_DISPUTED) {
        /* A report cannot dispute its result and release the same unresolved
         * claims. Previously established partial quiescence is not retracted. */
        e->receipt.reason = (e->flags & HMS_EP_CLOCK_QUALIFIED) != 0u ? 8u : 7u;
        fault(e, 8);
    } else e->receipt.held_mask = (uint8_t)(e->receipt.held_mask & (uint8_t)~r->quiescent_mask);
    drain_state(e);
}

static uint8_t owns_resources(const hms_endpoint *e) {
    uint8_t i, index = 0;
    const uint8_t *p = e->operation;
    if (e->receipt.held_mask != p[46]) return 0;
    for (i = 0; i < 8u; ++i) if ((p[46] & ((uint8_t)1u << i)) != 0u) {
        if (e->fence_floor[i] != get32(p + 88u + (uint16_t)index * 4u)) return 0;
        ++index;
    }
    return 1;
}

static uint8_t cutoff_reason(const hms_endpoint *e, uint8_t starting) {
    const uint8_t *p = e->operation;
    if ((e->flags & HMS_EP_CLOCK_QUALIFIED) == 0u) return 7;
    if (e->loss_reason != 0u) return e->loss_reason;
    if (e->now_tick >= get64(p + 80)) return 4;
    if (e->now_tick >= get64(p + 68)) return 3;
    if (e->receipt.started_at != HMS_EP_TIME_ABSENT && e->now_tick >= e->receipt.started_at &&
            e->now_tick - e->receipt.started_at >= get32(p + 76)) return 2;
    if (starting != 0u && e->now_tick >= get64(p + 60)) return 1;
    return 0;
}

static void poll_finite(hms_endpoint *e) {
    uint8_t phase, status, crossed;
    const uint8_t *p;
    hms_ep_report report;
    hms_ep_step_limits limits;
    if (e->operation_length == 0u) return;
    p = e->operation;
    if (terminal(e->receipt.execution) != 0u) {
        if (e->receipt.held_mask == 0u || e->receipt.verification == HMS_EP_DISPUTED) return;
        phase = HMS_EP_QUIESCENCE_STEP;
    } else if (e->receipt.execution == HMS_EP_QUEUED) {
        if (e->state != HMS_EP_ARMED || e->context_valid == 0u ||
                get32(p + 2) != e->control_generation || get16(p + 6) != e->context_handle || owns_resources(e) == 0u) { reject_queued(e, 6, 0); return; }
        if (e->now_tick < get64(p + 52)) return;
        if (e->now_tick >= get64(p + 60)) { reject_queued(e, 1, 0); return; }
        if (e->now_tick >= get64(p + 80)) { reject_queued(e, 4, 0); return; }
        status = guard_call(e, p);
        if (status != 0u) { reject_queued(e, 10, 0); return; }
        sample_clock(e);
        if (e->receipt.execution != HMS_EP_QUEUED) return;
        if (e->state != HMS_EP_ARMED || e->context_valid == 0u || owns_resources(e) == 0u) { reject_queued(e, 6, 0); return; }
        if (e->now_tick >= get64(p + 60)) { reject_queued(e, 1, 0); return; }
        if (e->now_tick >= get64(p + 80)) { reject_queued(e, 4, 0); return; }
        if (e->now_tick > UINT64_MAX - get32(p + 76)) { reject_queued(e, 2, 0); return; }
        if (revision(e) == 0u) return;
        e->receipt.execution = HMS_EP_RUNNING; e->receipt.may_have_acted = 1;
        e->receipt.started_at = e->now_tick; phase = HMS_EP_START;
    } else {
        if (e->loss_reason == 0u) {
            if (e->state == HMS_EP_FAULT) e->loss_reason = 7;
            else if (e->context_valid == 0u || get32(p + 2) != e->control_generation ||
                     get16(p + 6) != e->context_handle || owns_resources(e) == 0u) e->loss_reason = 6;
            else if (e->now_tick >= get64(p + 80)) e->loss_reason = 4;
            else if (e->now_tick >= get64(p + 68)) e->loss_reason = 3;
            else if (e->now_tick >= e->receipt.started_at && e->now_tick - e->receipt.started_at >= get32(p + 76)) e->loss_reason = 2;
            else if (guard_call(e, p) != 0u) e->loss_reason = 10;
        }
        sample_clock(e);
        crossed = cutoff_reason(e, 0);
        if (crossed != 0u) e->loss_reason = crossed;
        if (e->loss_reason != 0u || e->receipt.execution == HMS_EP_UNKNOWN) phase = HMS_EP_LOSS_STEP;
        else if (e->receipt.cancellation == HMS_EP_CANCEL_REQUESTED || e->receipt.cancellation == HMS_EP_CANCEL_ACK) phase = HMS_EP_CANCEL_STEP;
        else phase = HMS_EP_RUN;
    }
    limits.latest_start = get64(p + 60);
    limits.ordinary_until = get64(p + 68);
    if (get64(p + 80) < limits.ordinary_until) limits.ordinary_until = get64(p + 80);
    if (e->receipt.started_at != HMS_EP_TIME_ABSENT &&
            e->receipt.started_at <= UINT64_MAX - get32(p + 76) &&
            e->receipt.started_at + get32(p + 76) < limits.ordinary_until)
        limits.ordinary_until = e->receipt.started_at + get32(p + 76);
    memset(&report, 0, sizeof(report));
    e->callback_active = 1;
    e->config->step(e->config->user, phase, get16(p + 44), arguments(p), p[47], e->now_tick, &limits, &report);
    e->callback_active = 0;
    sample_clock(e);
    crossed = cutoff_reason(e, (uint8_t)(phase == HMS_EP_START));
    if (crossed != 0u && (report.terminal_state == HMS_EP_COMPLETED || phase == HMS_EP_START)) {
        /* No release or value from a possibly late report is consumed. */
        unknown_report(e, crossed); return;
    }
    if (crossed != 0u && terminal(e->receipt.execution) == 0u) e->loss_reason = crossed;
    apply_report(e, &report);
}

void hms_endpoint_poll(hms_endpoint *e, uint64_t now, uint16_t flags) {
    if (e == NULL || e->config == NULL || e->callback_active != 0u) return;
    update(e, now, flags);
    /* Sibling services: the finite report/limits frame is not retained while
     * the standing controller runs. Actual linked stack still needs analysis. */
    if (e->standing != NULL && e->standing->bytes[ST_SLOT] == ST_STANDING)
        hms_standing_poll(e->standing);
    else poll_finite(e);
}

void hms_endpoint_refresh(hms_endpoint *e, uint64_t now, uint16_t flags) { update(e, now, flags); }
void hms_endpoint_fresh_clock(hms_endpoint *e) { sample_clock(e); }
uint8_t hms_endpoint_readiness(const hms_endpoint *e) { return readiness(e); }
uint8_t hms_endpoint_bind_shared(hms_endpoint *e, const uint8_t *p) {
    if (e->standing != NULL && e->standing->bytes[ST_SLOT] != ST_EMPTY) return HMS_EP_BUSY;
    return bind_context(e, p);
}
uint8_t hms_endpoint_revoke_shared(hms_endpoint *e, const uint8_t *p) {
    if (get16(p + 8) != 6u) return HMS_EP_RESERVED;
    if (context_matches(e, p) == 0u) return HMS_EP_CONTEXT_MISMATCH;
    if (e->context_valid == 0u || (e->state != HMS_EP_BOUND && e->state != HMS_EP_ARMED)) return HMS_EP_BAD_STATE;
    invalidate(e, 6);
    return e->state == HMS_EP_FAULT ? HMS_EP_COUNTER_EXHAUSTED : HMS_EP_OK;
}
void hms_endpoint_counter_fault(hms_endpoint *e) { fault(e, 12); }
