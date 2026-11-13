/* BHMS-Compact endpoint state machine (spec/bhms/11-compact-binding.md 11.5-11.9).
 *
 * Design notes:
 *  - Replies are written synchronously through the HAL; there is no TX queue.
 *  - Every reply frame carries the current boot epoch as its session, so the
 *    epoch an operation ran in is visible on every STATUS/RESULT (BHMS-CMP-034).
 *  - An INVOKE refused with an ERROR other than 8/9/14 consumes no handle and
 *    no ring slot (it provably did not start), so its retransmission is simply
 *    evaluated again.
 */
#include <string.h>

#include "bhms.h"

typedef char bhms_assert_ring[(BHMS_RING_SIZE >= 4u && BHMS_MAX_ACTIVE >= 1u &&
                               BHMS_MAX_ACTIVE <= BHMS_RING_SIZE) ? 1 : -1];
typedef char bhms_assert_args[(BHMS_MAX_ARGS <= 182u && BHMS_MAX_RESULT <= 186u) ? 1 : -1];

/* ---- Flash table access ----------------------------------------------------- */
static void pgm_copy(void *dst, const void *src, size_t n) {
#if defined(__AVR__)
    memcpy_P(dst, src, n);
#else
    memcpy(dst, src, n);
#endif
}

static void load_action(const bhms_device *d, uint8_t idx, bhms_action *a) {
    pgm_copy(a, &d->actions[idx], sizeof *a);
}

static void load_field(const bhms_field *base, uint8_t idx, bhms_field *f) {
    pgm_copy(f, &base[idx], sizeof *f);
}

static uint8_t layout_bytes(const bhms_field *fields, uint8_t n) {
    uint8_t i, total = 0;
    for (i = 0; i < n; ++i) {
        bhms_field f;
        load_field(fields, i, &f);
        total = (uint8_t)(total + bhms_type_width(f.type));
    }
    return total;
}

/* ---- Little helpers --------------------------------------------------------- */
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }

static int is_active(const bhms_entry *e) {
    return e->stamp != 0 && (e->state == BHMS_ST_ACCEPTED || e->state == BHMS_ST_RUNNING);
}

static bhms_entry *find(bhms_endpoint *ep, uint16_t handle) {
    uint8_t i;
    for (i = 0; i < BHMS_RING_SIZE; ++i)
        if (ep->ring[i].stamp != 0 && ep->ring[i].handle == handle) return &ep->ring[i];
    return 0;
}

static uint8_t active_count(const bhms_endpoint *ep) {
    uint8_t i, n = 0;
    for (i = 0; i < BHMS_RING_SIZE; ++i)
        if (is_active(&ep->ring[i])) ++n;
    return n;
}

/* ---- Transmit --------------------------------------------------------------- */
static void send(bhms_endpoint *ep, uint8_t kind, const uint8_t *payload, size_t n) {
    bhms_frame_send(ep->hal, kind, BHMS_CHANNEL, ep->epoch, ep->tx_seq++, payload, n);
}

static void send_error(bhms_endpoint *ep, uint8_t req_type, uint16_t id, uint8_t code,
                       uint8_t detail) {
    uint8_t b[BHMS_LEN_ERROR];
    send(ep, BHMS_KIND_STATUS, b, bhms_enc_error(b, req_type, id, code, detail));
}

static void send_entry(bhms_endpoint *ep, const bhms_entry *e, uint8_t kind) {
    uint8_t b[BHMS_TX_PAYLOAD_CAP];
    size_t n;
    if (e->state >= BHMS_ST_COMPLETED)
        n = bhms_enc_result(b, e->handle, e->state, e->evidence, e->fault, e->res, e->res_len);
    else
        n = bhms_enc_status(b, e->handle, e->state, e->cancel, e->progress);
    send(ep, kind, b, n);
}

/* ---- Epoch ------------------------------------------------------------------ */
static uint32_t next_epoch(uint32_t e) {
    e = e + 1u;
    return e == 0u ? 1u : e;
}

static void reset_session_state(bhms_endpoint *ep) {
    uint8_t i;
    for (i = 0; i < BHMS_RING_SIZE; ++i) ep->ring[i].stamp = 0;
    ep->last_handle = 0;
    ep->fence_floor = 0;
    ep->max_fence = 0;
    ep->tx_seq = 0;
    ep->stop_pending = 0;
    ep->stamp_clock = 0;
}

/* Advance and (when the platform has a store) persist the epoch. */
/* `allow` is false when the stored counter could not be read (so the new value
 * may repeat an earlier one) or persistence was already lost: PERSISTENT_EPOCH
 * is then not claimed (BHMS-CMP-020) and no store is attempted. */
static void advance_epoch(bhms_endpoint *ep, uint32_t from, int allow) {
    ep->epoch = next_epoch(from);
    if (allow && ep->hal->epoch_load != 0 && ep->hal->epoch_store != 0)
        ep->persistent = ep->hal->epoch_store(ep->hal->ctx, ep->epoch) == 0 ? 1u : 0u;
    else
        ep->persistent = 0;
}

/* ep->dev stays NULL until everything succeeded; bhms_poll and the application
 * calls are no-ops on an endpoint whose dev is NULL. */
static bhms_err init_checked(bhms_endpoint *ep, const bhms_device *dev, const bhms_hal *hal) {
    uint8_t i, j;
    uint32_t stored = 0;
    int load_ok = 0;
    if (dev == 0 || hal == 0 || hal->uart_read == 0 || hal->uart_write == 0 ||
        hal->millis == 0)
        return BHMS_ERR_INVALID;
    if ((dev->n_actions != 0 && dev->actions == 0) ||
        (dev->n_properties != 0 && dev->properties == 0))
        return BHMS_ERR_INVALID;
    ep->hal = hal;
    for (i = 0; i < dev->n_actions; ++i) {
        bhms_action a;
        load_action(dev, i, &a);
        if (a.run == 0 || a.n_args > BHMS_MAX_FIELDS || a.n_results > BHMS_MAX_FIELDS ||
            (a.n_args != 0 && a.args == 0) || (a.n_results != 0 && a.results == 0))
            return BHMS_ERR_INVALID;
        for (j = 0; j < a.n_args; ++j) {
            bhms_field f;
            load_field(a.args, j, &f);
            if (bhms_type_width(f.type) == 0) return BHMS_ERR_INVALID;
        }
        for (j = 0; j < a.n_results; ++j) {
            bhms_field f;
            load_field(a.results, j, &f);
            if (bhms_type_width(f.type) == 0) return BHMS_ERR_INVALID;
        }
        {
            uint8_t ab = layout_bytes(a.args, a.n_args);
            if (ab > BHMS_MAX_ARGS || layout_bytes(a.results, a.n_results) > BHMS_MAX_RESULT)
                return BHMS_ERR_INVALID;
            if (ab > ep->max_args) ep->max_args = ab;
        }
    }
    for (i = 0; i < dev->n_properties; ++i) {
        bhms_property p;
        pgm_copy(&p, &dev->properties[i], sizeof p);
        if (p.read == 0 || bhms_type_width(p.field.type) == 0 ||
            bhms_type_width(p.field.type) > BHMS_MAX_RESULT)
            return BHMS_ERR_INVALID;
    }
    /* Boot counter first: no operation can be accepted before the epoch exists. */
    if (hal->epoch_load != 0 && hal->epoch_store != 0) {
        load_ok = hal->epoch_load(hal->ctx, &stored) == 0;
        if (!load_ok || stored == 0xFFFFFFFFu) stored = 0; /* unreadable or erased cell */
    }
    advance_epoch(ep, stored, load_ok);
    reset_session_state(ep);
    ep->dev = dev;
    return BHMS_OK;
}

bhms_err bhms_init(bhms_endpoint *ep, const bhms_device *dev, const bhms_hal *hal) {
    bhms_err err;
    if (ep == 0) return BHMS_ERR_INVALID;
    memset(ep, 0, sizeof *ep);
    err = init_checked(ep, dev, hal);
    if (err != BHMS_OK) memset(ep, 0, sizeof *ep); /* leave an inert endpoint */
    return err;
}

/* ---- Argument decoding and local limits ------------------------------------- */
static int in_range(const bhms_field *f, bhms_value v) {
    switch (f->type) {
    case BHMS_F32:
        /* NaN and infinities are never valid, with or without limits. */
        if (!(v.f - v.f == 0.0f)) return 0;
        return !f->has_range || (v.f >= f->flo && v.f <= f->fhi);
    case BHMS_U8: case BHMS_U16: case BHMS_U32:
        return !f->has_range || (v.u >= (uint32_t)f->ilo && v.u <= (uint32_t)f->ihi);
    case BHMS_BOOL:
        return 1;
    default: /* signed */
        return !f->has_range || (v.i >= f->ilo && v.i <= f->ihi);
    }
}

/* Returns 0, or -1 with code and detail set. */
static int decode_args(const bhms_action *a, const uint8_t *p, bhms_value *vals, uint8_t *code,
                       uint8_t *detail) {
    uint8_t i;
    for (i = 0; i < a->n_args; ++i) {
        bhms_field f;
        load_field(a->args, i, &f);
        if (bhms_value_get(f.type, p, &vals[i]) != 0) {
            *code = BHMS_E_MALFORMED;
            *detail = i;
            return -1;
        }
        if (!in_range(&f, vals[i])) {
            *code = BHMS_E_OUT_OF_RANGE;
            *detail = i;
            return -1;
        }
        p += bhms_type_width(f.type);
    }
    return 0;
}

static size_t encode_results(const bhms_action *a, const bhms_value *vals, uint8_t *out) {
    uint8_t i;
    size_t n = 0;
    for (i = 0; i < a->n_results; ++i) {
        bhms_field f;
        load_field(a->results, i, &f);
        bhms_value_put(f.type, vals[i], out + n);
        n += bhms_type_width(f.type);
    }
    return n;
}

/* ---- Operation lifecycle ---------------------------------------------------- */
static bhms_entry *claim_slot(bhms_endpoint *ep) {
    uint8_t i;
    bhms_entry *victim = 0;
    for (i = 0; i < BHMS_RING_SIZE; ++i) {
        bhms_entry *e = &ep->ring[i];
        if (e->stamp == 0) return e;
        if (!is_active(e) && (victim == 0 || e->stamp < victim->stamp)) victim = e;
    }
    return victim; /* oldest terminal entry, or NULL when the ring is all active */
}

static void finish_entry(bhms_endpoint *ep, bhms_entry *e, uint8_t state, uint8_t evidence,
                         uint8_t fault, const bhms_value *results, uint8_t kind) {
    e->state = state;
    e->evidence = evidence;
    e->fault = fault;
    e->progress = state == BHMS_ST_COMPLETED ? 100u : e->progress;
    if (state == BHMS_ST_CANCELED) e->cancel = BHMS_CANCEL_CONFIRMED;
    e->res_len = 0;
    if (state == BHMS_ST_COMPLETED && results != 0) {
        bhms_action a;
        load_action(ep->dev, e->inv[0], &a);
        e->res_len = (uint8_t)encode_results(&a, results, e->res);
    }
    send_entry(ep, e, kind);
}

static void handle_invoke(bhms_endpoint *ep, const uint8_t *p, size_t n, uint32_t rx_ms) {
    bhms_invoke inv;
    bhms_entry *e;
    bhms_action a;
    bhms_call call;
    bhms_value args[BHMS_MAX_FIELDS];
    uint8_t code = 0, detail = 0, ret;
    uint16_t prev_last;

    (void)bhms_dec_invoke(p, n, &inv); /* n >= 10 was checked by the caller */
    if (inv.handle == 0) {
        send_error(ep, BHMS_MSG_INVOKE, 0, BHMS_E_MALFORMED, 0);
        return;
    }
    e = find(ep, inv.handle);
    if (e != 0) { /* BHMS-CMP-032: replay */
        if (e->inv_len == n - 3u && memcmp(e->inv, p + 3, e->inv_len) == 0)
            send_entry(ep, e, BHMS_KIND_STATUS);
        else
            send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_HANDLE_CONFLICT, 0);
        return;
    }
    if (inv.handle <= ep->last_handle) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_HANDLE_UNKNOWN, 0);
        return;
    }
    if (inv.action >= ep->dev->n_actions) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_UNKNOWN_ACTION, inv.action);
        return;
    }
    load_action(ep->dev, inv.action, &a);
    if (inv.n_args != layout_bytes(a.args, a.n_args)) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_MALFORMED, 0);
        return;
    }
    /* BHMS-CMP-040: the fence is judged, and the floor raised, before any later
     * refusal (INHIBITED, EXPIRED, OUT_OF_RANGE, BUSY): a refused INVOKE with a
     * newer fence still fences older leases. Frames refused above this point
     * (bad handle, action or length) never touch the fence state. */
    if ((ep->dev->flags & BHMS_DEV_FENCING) != 0) {
        if (inv.fence != 0 && inv.fence < ep->fence_floor) {
            send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_FENCED, 0);
            return;
        }
        if (inv.fence == 0 && (a.flags & BHMS_ACT_REQUIRES_LEASE) != 0) {
            send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_LEASE_REQUIRED, 0);
            return;
        }
    }
    if (inv.fence > ep->max_fence) ep->max_fence = inv.fence;
    if ((ep->dev->flags & BHMS_DEV_FENCING) != 0 && inv.fence > ep->fence_floor)
        ep->fence_floor = inv.fence;
    if (ep->inhibit || ep->pin_asserted) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_INHIBITED, 0);
        return;
    }
    if (inv.ttl_ms != 0 && (uint32_t)(ep->hal->millis(ep->hal->ctx) - rx_ms) > inv.ttl_ms) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_EXPIRED, 0);
        return;
    }
    if (decode_args(&a, inv.args, args, &code, &detail) != 0) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, code, detail);
        return;
    }
    e = claim_slot(ep);
    if (e == 0 || active_count(ep) >= BHMS_MAX_ACTIVE) {
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, BHMS_E_BUSY, 0);
        return;
    }
    /* Accepted: from here the handle is consumed. */
    prev_last = ep->last_handle;
    ep->last_handle = inv.handle;
    memset(e, 0, sizeof *e);
    e->stamp = ++ep->stamp_clock;
    e->handle = inv.handle;
    e->state = BHMS_ST_ACCEPTED;
    e->cancel = BHMS_CANCEL_NONE;
    e->progress = BHMS_PROGRESS_UNKNOWN;
    e->inv_len = (uint8_t)(n - 3u);
    memcpy(e->inv, p + 3, e->inv_len);

    memset(&call, 0, sizeof call);
    call.handle = inv.handle;
    call.evidence = BHMS_EV_REPORTED;
    call.error = BHMS_E_PRECONDITION;
    ret = a.run(ep->dev->user, args, &call);
    if (e->state >= BHMS_ST_COMPLETED) return; /* the callback finished it itself */
    switch (ret) {
    case BHMS_RUN_DONE:
        finish_entry(ep, e, BHMS_ST_COMPLETED, call.evidence, 0, call.results, BHMS_KIND_STATUS);
        break;
    case BHMS_RUN_STARTED:
        e->state = BHMS_ST_RUNNING;
        send_entry(ep, e, BHMS_KIND_STATUS);
        break;
    case BHMS_RUN_FAILED:
        finish_entry(ep, e, BHMS_ST_FAILED, call.evidence, call.fault, 0, BHMS_KIND_STATUS);
        break;
    default: /* REJECTED (or a bad return code): not started, nothing retained */
        e->stamp = 0;
        ep->last_handle = prev_last;
        if (ret != BHMS_RUN_REJECTED || call.error == BHMS_E_HANDLE_UNKNOWN ||
            call.error == BHMS_E_SESSION_MISMATCH || call.error == BHMS_E_HANDLE_CONFLICT ||
            call.error == 0)
            call.error = ret == BHMS_RUN_REJECTED ? BHMS_E_PRECONDITION : BHMS_E_INTERNAL;
        send_error(ep, BHMS_MSG_INVOKE, inv.handle, call.error, 0);
        break;
    }
}

static void handle_cancel(bhms_endpoint *ep, uint16_t handle) {
    bhms_entry *e = find(ep, handle);
    bhms_action a;
    uint8_t r;
    if (e == 0) {
        send_error(ep, BHMS_MSG_CANCEL, handle, BHMS_E_HANDLE_UNKNOWN, 0);
        return;
    }
    if (!is_active(e)) { /* already terminal: idempotent, answer with the RESULT */
        send_entry(ep, e, BHMS_KIND_STATUS);
        return;
    }
    load_action(ep->dev, e->inv[0], &a);
    e->cancel = BHMS_CANCEL_REQUESTED;
    r = a.cancel != 0 ? a.cancel(ep->dev->user, handle) : (uint8_t)BHMS_CANCEL_REFUSED;
    if (e->state != BHMS_ST_ACCEPTED && e->state != BHMS_ST_RUNNING) return; /* ended inside */
    if (r == BHMS_CANCEL_CONFIRMED) {
        finish_entry(ep, e, BHMS_ST_CANCELED, BHMS_EV_REPORTED, 0, 0, BHMS_KIND_STATUS);
    } else {
        e->cancel = r == BHMS_CANCEL_ACK ? BHMS_CANCEL_ACK : BHMS_CANCEL_REFUSED;
        send_entry(ep, e, BHMS_KIND_STATUS);
    }
}

static void handle_read(bhms_endpoint *ep, const uint8_t *p) {
    uint16_t request = rd16(p + 1);
    uint8_t idx = p[3], quality, k;
    bhms_property prop;
    bhms_value v;
    bhms_sample meta;
    uint8_t b[BHMS_LEN_VALUE_FIXED + 4u];
    if (idx >= ep->dev->n_properties) {
        send_error(ep, BHMS_MSG_READ, request, BHMS_E_UNKNOWN_PROPERTY, idx);
        return;
    }
    pgm_copy(&prop, &ep->dev->properties[idx], sizeof prop);
    v.u = 0;
    meta.evidence = BHMS_VEV_MEASURED;
    meta.age_ms = BHMS_AGE_UNKNOWN;
    quality = prop.read(ep->dev->user, (uint8_t)((p[4] & BHMS_READ_FRESH) != 0), &v, &meta);
    if (quality > BHMS_Q_UNKNOWN) quality = BHMS_Q_UNKNOWN;
    k = (quality == BHMS_Q_INVALID || quality == BHMS_Q_UNKNOWN) ? 0u
                                                                : bhms_type_width(prop.field.type);
    if (k != 0) bhms_value_put(prop.field.type, v, b + BHMS_LEN_VALUE_FIXED);
    send(ep, BHMS_KIND_STATUS, b,
         bhms_enc_value(b, request, idx, quality, meta.evidence, ++ep->value_seq, meta.age_ms,
                        b + BHMS_LEN_VALUE_FIXED, k));
}

/* BHMS-CMP-050/051. `solicited` selects kind 02 (reply) or 03 (pin / local). */
static void do_stop(bhms_endpoint *ep, uint8_t reason, uint8_t solicited) {
    uint8_t outcome = BHMS_STOPACK_UNSUPPORTED, evidence = BHMS_EV_NONE, count = 0, i;
    uint8_t b[BHMS_LEN_STOP_ACK];
    uint8_t ended[BHMS_RING_SIZE];
    if (ep->dev->stop != 0) outcome = ep->dev->stop(ep->dev->user, reason, &evidence);
    if (outcome > BHMS_STOPACK_UNSUPPORTED) outcome = BHMS_STOPACK_UNSUPPORTED;
    for (i = 0; i < BHMS_RING_SIZE; ++i) {
        bhms_entry *e = &ep->ring[i];
        ended[i] = 0;
        if (!is_active(e)) continue;
        {
            bhms_action a;
            load_action(ep->dev, e->inv[0], &a);
            if (a.cancel != 0) (void)a.cancel(ep->dev->user, e->handle);
        }
        e->state = BHMS_ST_CANCELED;
        e->cancel = BHMS_CANCEL_CONFIRMED;
        e->evidence = evidence;
        e->fault = 0;
        e->res_len = 0;
        ended[i] = 1;
        ++count;
    }
    /* Fence everything seen so far (saturating). */
    if (ep->max_fence != 0xFFFFFFFFu && ep->max_fence + 1u > ep->fence_floor)
        ep->fence_floor = ep->max_fence + 1u;
    else if (ep->max_fence == 0xFFFFFFFFu)
        ep->fence_floor = 0xFFFFFFFFu;
    ep->stop_pending = outcome == BHMS_STOPACK_INITIATED;
    ep->stop_count = count;
    send(ep, solicited ? BHMS_KIND_STATUS : BHMS_KIND_TELEMETRY, b,
         bhms_enc_stop_ack(b, outcome, evidence, count));
    for (i = 0; i < BHMS_RING_SIZE; ++i)
        if (ended[i]) send_entry(ep, &ep->ring[i], BHMS_KIND_TELEMETRY);
}

static void handle_hello_req(bhms_endpoint *ep, const uint8_t *p) {
    uint8_t b[BHMS_LEN_HELLO], flags = 0;
    bhms_hello_req req;
    (void)bhms_dec_hello_req(p, BHMS_LEN_HELLO_REQ, &req);
    if (req.version != BHMS_VERSION) {
        send_error(ep, BHMS_MSG_HELLO_REQ, 0, BHMS_E_UNSUPPORTED, BHMS_VERSION);
        return;
    }
    /* BHMS-CMP-023: honoured only when nothing is active, otherwise ignored. */
    if ((req.flags & BHMS_HELLO_REQ_NEW_SESSION) != 0 && active_count(ep) == 0) {
        advance_epoch(ep, ep->epoch, ep->persistent);
        reset_session_state(ep);
    }
    if ((ep->dev->flags & BHMS_DEV_FENCING) != 0) flags |= BHMS_HELLO_FENCING;
    if (ep->persistent) flags |= BHMS_HELLO_PERSISTENT_EPOCH;
    if (ep->dev->stop != 0) flags |= BHMS_HELLO_STOP_SUPPORTED;
    send(ep, BHMS_KIND_STATUS, b,
         bhms_enc_hello(b, flags, ep->dev->digest8, ep->epoch, req.nonce, ep->last_handle,
                        BHMS_RING_SIZE, BHMS_MAX_ACTIVE, ep->max_args));
}

static void dispatch(bhms_endpoint *ep, const uint8_t *raw, uint32_t rx_ms) {
    const uint8_t *p = raw + HMS_FRAME_HEADER;
    size_t n = ((size_t)raw[18] << 8) | raw[19];
    uint8_t type, i;
    uint16_t id = 0;
    uint64_t session = 0;
    size_t expect = 0;

    if (raw[3] != BHMS_KIND_CONTROL || raw[5] != BHMS_CHANNEL) return; /* CMP-001 */
    for (i = 0; i < 8u; ++i) session = (session << 8) | raw[6 + i];
    if (n == 0) {
        send_error(ep, 0, 0, BHMS_E_MALFORMED, 0);
        return;
    }
    type = p[0];
    if (n >= 3u) id = rd16(p + 1);
    switch (type) { /* BHMS-CMP-002: exact lengths */
    case BHMS_MSG_HELLO_REQ: expect = BHMS_LEN_HELLO_REQ; break;
    case BHMS_MSG_CANCEL: expect = BHMS_LEN_CANCEL; break;
    case BHMS_MSG_READ: expect = BHMS_LEN_READ; break;
    case BHMS_MSG_STOP: expect = BHMS_LEN_STOP; break;
    case BHMS_MSG_QUERY: expect = BHMS_LEN_QUERY; break;
    case BHMS_MSG_INVOKE:
        if (n < BHMS_LEN_INVOKE_FIXED) expect = BHMS_LEN_INVOKE_FIXED;
        else expect = n;
        break;
    default:
        send_error(ep, type, id, BHMS_E_MALFORMED, 0);
        return;
    }
    if (n != expect) {
        send_error(ep, type, id, BHMS_E_MALFORMED, 0);
        return;
    }
    if (type != BHMS_MSG_HELLO_REQ && type != BHMS_MSG_STOP && session != ep->epoch) {
        send_error(ep, type, id, BHMS_E_SESSION_MISMATCH, 0); /* BHMS-CMP-021 */
        return;
    }
    switch (type) {
    case BHMS_MSG_HELLO_REQ: handle_hello_req(ep, p); break;
    case BHMS_MSG_INVOKE: handle_invoke(ep, p, n, rx_ms); break;
    case BHMS_MSG_CANCEL: handle_cancel(ep, id); break;
    case BHMS_MSG_READ: handle_read(ep, p); break;
    case BHMS_MSG_STOP: do_stop(ep, p[1], 1); break;
    default: { /* QUERY (BHMS-CMP-034/035) */
        bhms_entry *e = find(ep, id);
        if (e != 0) send_entry(ep, e, BHMS_KIND_STATUS);
        else send_error(ep, BHMS_MSG_QUERY, id, BHMS_E_HANDLE_UNKNOWN, 0);
        break;
    }
    }
}

void bhms_poll(bhms_endpoint *ep) {
    uint16_t budget;
    uint32_t now;
    int pin;
    if (ep == 0 || ep->dev == 0) return; /* not initialised (or init failed) */
    now = ep->hal->millis(ep->hal->ctx);
    pin = ep->hal->stop_pin != 0 && ep->hal->stop_pin(ep->hal->ctx) != 0;

    if (pin && !ep->pin_asserted) {
        ep->pin_asserted = 1;
        do_stop(ep, BHMS_STOP_OPERATOR, 0);
    } else if (!pin) {
        ep->pin_asserted = 0;
    }
    if (ep->rx_started && (uint32_t)(now - ep->frame_start_ms) > BHMS_RX_TIMEOUT_MS) {
        hms_frame_reset(&ep->parser); /* absolute deadline: trickling does not renew it */
        ep->rx_started = 0;
        ++ep->bad_frames;
    }
    for (budget = 0; budget < BHMS_POLL_MAX_BYTES; ++budget) {
        hms_frame_result r;
        int c = ep->hal->uart_read(ep->hal->ctx);
        if (c < 0) break;
        if (c != 0x7e && !ep->rx_started) {
            ep->rx_started = 1;
            ep->frame_start_ms = ep->hal->millis(ep->hal->ctx);
        }
        r = hms_frame_feed(&ep->parser, (uint8_t)c);
        if (c == 0x7e) ep->rx_started = 0;
        if (r == HMS_FRAME_READY) {
            dispatch(ep, ep->parser.raw, ep->frame_start_ms);
        } else if (r == HMS_FRAME_INVALID || r == HMS_FRAME_OVERFLOW) {
            ++ep->bad_frames;
            if (r == HMS_FRAME_OVERFLOW) ep->rx_started = 0;
        }
    }
}

/* ---- Application-facing completion API -------------------------------------- */
bhms_err bhms_op_finish(bhms_endpoint *ep, uint16_t handle, uint8_t state, uint8_t evidence,
                        uint8_t fault, const bhms_value *results) {
    bhms_entry *e;
    bhms_action a;
    if (ep == 0 || ep->dev == 0) return BHMS_ERR_INVALID;
    e = find(ep, handle);
    if (state < BHMS_ST_COMPLETED || state > BHMS_ST_REJECTED) return BHMS_ERR_INVALID;
    if (e == 0) return BHMS_ERR_NO_ENTRY;
    if (!is_active(e)) return BHMS_ERR_STATE;
    load_action(ep->dev, e->inv[0], &a);
    if (state == BHMS_ST_COMPLETED && a.n_results != 0 && results == 0) return BHMS_ERR_INVALID;
    finish_entry(ep, e, state, evidence, fault, results, BHMS_KIND_TELEMETRY);
    return BHMS_OK;
}

bhms_err bhms_op_progress(bhms_endpoint *ep, uint16_t handle, uint8_t percent) {
    bhms_entry *e;
    if (ep == 0 || ep->dev == 0) return BHMS_ERR_INVALID;
    e = find(ep, handle);
    if (percent > 100u) return BHMS_ERR_INVALID;
    if (e == 0) return BHMS_ERR_NO_ENTRY;
    if (!is_active(e)) return BHMS_ERR_STATE;
    e->state = BHMS_ST_RUNNING;
    e->progress = percent;
    send_entry(ep, e, BHMS_KIND_TELEMETRY);
    return BHMS_OK;
}

bhms_err bhms_publish(bhms_endpoint *ep, uint8_t property_index) {
    bhms_property prop;
    bhms_value v;
    bhms_sample meta;
    uint8_t quality, k;
    uint8_t b[BHMS_LEN_VALUE_FIXED + 4u];
    if (ep == 0 || ep->dev == 0 || property_index >= ep->dev->n_properties) return BHMS_ERR_INVALID;
    pgm_copy(&prop, &ep->dev->properties[property_index], sizeof prop);
    v.u = 0;
    meta.evidence = BHMS_VEV_MEASURED;
    meta.age_ms = BHMS_AGE_UNKNOWN;
    quality = prop.read(ep->dev->user, 0, &v, &meta);
    if (quality > BHMS_Q_UNKNOWN) quality = BHMS_Q_UNKNOWN;
    k = (quality == BHMS_Q_INVALID || quality == BHMS_Q_UNKNOWN) ? 0u
                                                                : bhms_type_width(prop.field.type);
    if (k != 0) bhms_value_put(prop.field.type, v, b + BHMS_LEN_VALUE_FIXED);
    send(ep, BHMS_KIND_TELEMETRY, b,
         bhms_enc_value(b, 0, property_index, quality, meta.evidence, ++ep->value_seq,
                        meta.age_ms, b + BHMS_LEN_VALUE_FIXED, k));
    return BHMS_OK;
}

void bhms_stop_confirmed(bhms_endpoint *ep, uint8_t evidence) {
    uint8_t b[BHMS_LEN_STOP_ACK];
    if (ep == 0 || ep->dev == 0 || !ep->stop_pending) return;
    ep->stop_pending = 0;
    send(ep, BHMS_KIND_TELEMETRY, b,
         bhms_enc_stop_ack(b, BHMS_STOPACK_CONFIRMED, evidence, ep->stop_count));
}

void bhms_set_inhibit(bhms_endpoint *ep, uint8_t inhibited) {
    if (ep == 0 || ep->dev == 0) return;
    ep->inhibit = inhibited ? 1u : 0u;
}
