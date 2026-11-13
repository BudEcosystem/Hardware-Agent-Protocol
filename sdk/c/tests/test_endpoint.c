/* Endpoint state-machine tests over the in-memory host HAL. A scripted gateway
 * feeds frames; every reply is parsed back with the reused C frame parser. */
#include <math.h>
#include <stdlib.h>

#include "bhms.h"
#include "bhms_hal_host.h"
#include "bhms_test.h"

/* ---- Test device: LED, async mover, faulty/rejecting actions, two properties - */
static struct {
    unsigned led_calls, move_calls, last_led;
    uint8_t cancel_mode; /* returns BHMS_CANCEL_* */
    uint8_t stop_mode;   /* BHMS_STOPACK_* */
    unsigned stops;
    bhms_endpoint *ep; /* for callbacks that call back into the library */
    uint8_t quality;
    uint16_t adc;
    uint8_t fresh_seen;
    uint8_t reject_error;
} g;

static uint8_t led_run(void *u, const bhms_value *a, bhms_call *c) {
    (void)u;
    g.last_led = a[0].u;
    c->results[0].u = ++g.led_calls;
    c->evidence = BHMS_EV_REPORTED;
    return BHMS_RUN_DONE;
}
static uint8_t move_run(void *u, const bhms_value *a, bhms_call *c) {
    (void)u; (void)a; (void)c;
    ++g.move_calls;
    return BHMS_RUN_STARTED;
}
static uint8_t move_cancel(void *u, uint16_t h) { (void)u; (void)h; return g.cancel_mode; }
static uint8_t fail_run(void *u, const bhms_value *a, bhms_call *c) {
    (void)u; (void)a;
    c->fault = 7;
    c->evidence = BHMS_EV_MEASURED;
    return BHMS_RUN_FAILED;
}
static uint8_t reject_run(void *u, const bhms_value *a, bhms_call *c) {
    (void)u; (void)a;
    c->error = g.reject_error;
    return BHMS_RUN_REJECTED;
}
static uint8_t progress_run(void *u, const bhms_value *a, bhms_call *c) {
    (void)u; (void)a;
    /* Reporting progress from inside run, then finishing synchronously. */
    CHECK(bhms_op_progress(g.ep, c->handle, 50) == BHMS_OK);
    return BHMS_RUN_DONE;
}
static uint8_t adc_read(void *u, uint8_t fresh, bhms_value *o, bhms_sample *m) {
    (void)u;
    g.fresh_seen = fresh;
    o->u = g.adc;
    m->evidence = BHMS_VEV_MEASURED;
    m->age_ms = 5;
    return g.quality;
}
static uint8_t temp_read(void *u, uint8_t fresh, bhms_value *o, bhms_sample *m) {
    (void)u; (void)fresh; (void)m;
    o->f = 21.5f;
    return BHMS_Q_VALID;
}
static uint8_t dev_stop(void *u, uint8_t reason, uint8_t *ev) {
    (void)u; (void)reason;
    ++g.stops;
    *ev = BHMS_EV_MEASURED;
    return g.stop_mode;
}

BHMS_FIELDS(led_args) = {BHMS_BOOL()};
BHMS_FIELDS(led_res) = {BHMS_U8()};
BHMS_FIELDS(move_args) = {BHMS_F32_RANGE(0, 200), BHMS_U16_RANGE(1, 1000), BHMS_I8_RANGE(-5, 5)};
BHMS_FIELDS(move_res) = {BHMS_U16()};
static const bhms_action kActions[] BHMS_PROGMEM = {
    BHMS_ACTION(led_run, 0, 0, BHMS_FIELDS_REF(led_args), BHMS_FIELDS_REF(led_res)),
    BHMS_ACTION(move_run, move_cancel, BHMS_ACT_REQUIRES_LEASE, BHMS_FIELDS_REF(move_args),
                BHMS_FIELDS_REF(move_res)),
    BHMS_ACTION(fail_run, 0, 0, BHMS_NO_FIELDS, BHMS_NO_FIELDS),
    BHMS_ACTION(reject_run, 0, 0, BHMS_NO_FIELDS, BHMS_NO_FIELDS),
    BHMS_ACTION(progress_run, 0, 0, BHMS_NO_FIELDS, BHMS_NO_FIELDS),
};
static const bhms_property kProps[] BHMS_PROGMEM = {
    BHMS_PROPERTY(adc_read, BHMS_U16),
    BHMS_PROPERTY(temp_read, BHMS_F32),
};
static const bhms_device kDev = {
    {0xde, 0xad, 0xbe, 0xef, 1, 2, 3, 4}, BHMS_DEV_FENCING, kActions, 5, kProps, 2, dev_stop, 0};
static const bhms_device kDevNoStop = {
    {0xde, 0xad, 0xbe, 0xef, 1, 2, 3, 4}, 0, kActions, 5, kProps, 2, 0, 0};

/* ---- Harness ---------------------------------------------------------------- */
typedef struct {
    bhms_host host;
    bhms_endpoint ep;
    uint32_t gseq;
} rig;

static void rig_boot(rig *r, int persistent, const bhms_device *dev) {
    memset(&g, 0, sizeof g);
    g.quality = BHMS_Q_VALID;
    g.adc = 0x155;
    g.cancel_mode = BHMS_CANCEL_ACK;
    g.stop_mode = BHMS_STOPACK_CONFIRMED;
    g.reject_error = BHMS_E_PRECONDITION;
    g.ep = &r->ep;
    bhms_host_init(&r->host, persistent);
    r->gseq = 0;
    CHECK(bhms_init(&r->ep, dev, &r->host.hal) == BHMS_OK);
}

/* Reboot keeping the EEPROM cell. */
static void rig_reboot(rig *r) {
    uint32_t cell = r->host.eeprom;
    int per = r->host.has_eeprom;
    uint32_t now = r->host.now_ms;
    bhms_host_init(&r->host, per);
    r->host.eeprom = cell;
    r->host.now_ms = now;
    CHECK(bhms_init(&r->ep, &kDev, &r->host.hal) == BHMS_OK);
}

static void gsend(rig *r, uint64_t session, const uint8_t *payload, size_t n) {
    CHECK(bhms_host_feed_frame(&r->host, BHMS_KIND_CONTROL, BHMS_CHANNEL, session, r->gseq++,
                               payload, n) == 0);
    for (int i = 0; i < 64 && (i == 0 || r->host.rx_len > 0); ++i) bhms_poll(&r->ep);
}

static int next(rig *r, bhms_host_frame *f) { return bhms_host_next_tx(&r->host, f); }

/* Expect exactly one pending frame, of the given kind and first payload byte. */
static int expect_one(rig *r, bhms_host_frame *f, uint8_t kind, uint8_t type) {
    int rc_ = next(r, f); int ok = rc_ == 1 && f->kind == kind && f->payload[0] == type && f->channel == 1; if (!ok) fprintf(stderr, "expect_one: rc=%d kind=%u type=%02x len=%u\n", rc_, rc_==1?f->kind:0, rc_==1?f->payload[0]:0, rc_==1?f->length:0);
    CHECK(ok);
    CHECK(bhms_host_tx_pending(&r->host) == 0);
    return ok;
}

static void expect_error(rig *r, uint8_t req_type, uint16_t id, uint8_t code) {
    bhms_host_frame f;
    bhms_error e;
    if (!expect_one(r, &f, BHMS_KIND_STATUS, BHMS_MSG_ERROR)) return;
    CHECK(bhms_dec_error(f.payload, f.length, &e) == 0);
    CHECK(e.request_type == req_type && (id == 0xFFFFu || e.id == id) && e.code == code);
}

static uint64_t hello(rig *r, uint8_t flags, uint32_t nonce, bhms_hello *out) {
    uint8_t b[16];
    bhms_host_frame f;
    gsend(r, 0, b, bhms_enc_hello_req(b, flags, nonce));
    CHECK(next(r, &f) == 1);
    CHECK(bhms_dec_hello(f.payload, f.length, out) == 0);
    CHECK(f.session == out->epoch && out->nonce == nonce);
    return f.session;
}

static void invoke(rig *r, uint64_t epoch, uint16_t handle, uint8_t action, uint32_t fence,
                   uint16_t ttl, const uint8_t *args, size_t n) {
    uint8_t b[64];
    gsend(r, epoch, b, bhms_enc_invoke(b, handle, action, fence, ttl, args, n));
}

static const uint8_t kOn[1] = {1};
static const uint8_t kOn2[2] = {1, 1};
static const uint8_t kMoveArgs[7] = {0x00, 0x00, 0x48, 0x42, 0xE8, 0x03, 0x00}; /* 50.0f, 1000, 0 */

/* ---- Tests ------------------------------------------------------------------ */
static void test_hello_and_epoch(void) {
    rig r;
    bhms_hello h;
    rig_boot(&r, 0, &kDev);
    uint64_t e = hello(&r, 0, 0xCAFE, &h);
    CHECK(e == 1);
    CHECK(h.version == 1 && h.flags == (BHMS_HELLO_FENCING | BHMS_HELLO_STOP_SUPPORTED));
    CHECK(h.last_handle == 0 && h.ring == BHMS_RING_SIZE && h.max_active == BHMS_MAX_ACTIVE);
    CHECK(h.max_args == 7);
    static const uint8_t dg[8] = {0xde, 0xad, 0xbe, 0xef, 1, 2, 3, 4};
    CHECK_BYTES(h.digest8, dg, 8);
    CHECK(bhms_host_tx_pending(&r.host) == 0);

    /* No store: epoch repeats after a reboot and PERSISTENT_EPOCH is clear. */
    rig_reboot(&r);
    CHECK(hello(&r, 0, 1, &h) == 1);
    CHECK((h.flags & BHMS_HELLO_PERSISTENT_EPOCH) == 0);

    /* Device without stop and fencing. */
    rig_boot(&r, 0, &kDevNoStop);
    hello(&r, 0, 2, &h);
    CHECK(h.flags == 0);
}

static void test_persistent_epoch(void) {
    rig r;
    bhms_hello h;
    rig_boot(&r, 1, &kDev); /* erased cell */
    CHECK(hello(&r, 0, 1, &h) == 1);
    CHECK(h.flags & BHMS_HELLO_PERSISTENT_EPOCH);
    CHECK(r.host.eeprom == 1 && r.host.eeprom_writes == 1);
    rig_reboot(&r);
    CHECK(hello(&r, 0, 2, &h) == 2);
    rig_reboot(&r);
    CHECK(hello(&r, 0, 3, &h) == 3);
    CHECK(r.host.eeprom == 3);

    /* The epoch survives into a reboot only through the cell: wrap skips zero. */
    r.host.eeprom = 0xFFFFFFFEu;
    rig_reboot(&r);
    hello(&r, 0, 4, &h);
    CHECK(h.epoch == 0xFFFFFFFFu);

    /* A failing store clears PERSISTENT_EPOCH (CMP-020) but still advances. */
    rig_boot(&r, 1, &kDev);
    r.host.store_fails = 1;
    CHECK(bhms_init(&r.ep, &kDev, &r.host.hal) == BHMS_OK);
    hello(&r, 0, 5, &h);
    CHECK((h.flags & BHMS_HELLO_PERSISTENT_EPOCH) == 0 && h.epoch != 0);

    /* HELLO_REQ with an unsupported version is refused. */
    rig_boot(&r, 0, &kDev);
    uint8_t b[16];
    size_t n = bhms_enc_hello_req(b, 0, 9);
    b[1] = 2;
    gsend(&r, 0, b, n);
    expect_error(&r, BHMS_MSG_HELLO_REQ, 0, BHMS_E_UNSUPPORTED);
}

static void test_invoke_result_exact(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1);
    CHECK(f.kind == BHMS_KIND_STATUS && f.session == e);
    static const uint8_t want[] = {0x83, 0x01, 0x00, 0x03, 0x01, 0x00, 0x01};
    CHECK(f.length == sizeof want);
    CHECK_BYTES(f.payload, want, sizeof want);
    CHECK(g.led_calls == 1 && g.last_led == 1);
    CHECK(bhms_host_tx_pending(&r.host) == 0);

    /* Frame sequence counts per epoch from 0 and is diagnostic only. */
    CHECK(f.sequence == 1); /* HELLO was sequence 0 */
}

static void test_replay_ring(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f1, f2;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f1) == 1);
    /* Retransmit: identical payload -> same RESULT, handler not run again. */
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f2) == 1);
    CHECK(f1.length == f2.length && memcmp(f1.payload, f2.payload, f1.length) == 0);
    CHECK(g.led_calls == 1);
    CHECK(f2.sequence == f1.sequence + 1); /* sequence is not a dedup key */

    /* Same handle, different payload -> HANDLE_CONFLICT, no action. */
    uint8_t off = 0;
    invoke(&r, e, 1, 0, 0, 0, &off, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_HANDLE_CONFLICT);
    CHECK(g.led_calls == 1);
    /* Same args but different fence is a different payload. */
    invoke(&r, e, 1, 0, 9, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_HANDLE_CONFLICT);

    /* Handles 2..5 push handle 1 out of the 4-entry ring. */
    for (uint16_t hnd = 2; hnd <= 5; ++hnd) {
        invoke(&r, e, hnd, 0, 0, 0, kOn, 1);
        CHECK(next(&r, &f1) == 1);
    }
    CHECK(g.led_calls == 5);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1); /* <= lastHandle, not in ring */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_HANDLE_UNKNOWN);
    CHECK(g.led_calls == 5);
    invoke(&r, e, 5, 0, 0, 0, kOn, 1); /* still in the ring */
    CHECK(next(&r, &f1) == 1 && f1.payload[0] == BHMS_MSG_RESULT);
    CHECK(g.led_calls == 5);
    /* An out-of-order lower handle that was never used is also refused. */
    invoke(&r, e, 20, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f1) == 1);
    invoke(&r, e, 10, 0, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 10, BHMS_E_HANDLE_UNKNOWN);
    CHECK(g.led_calls == 6);
}

static void test_query_and_epoch_in_replies(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[8];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.session == 1);
    /* QUERY in the same incarnation: RESULT again, stamped with the epoch. */
    gsend(&r, e, b, bhms_enc_query(b, 1));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.session == e);
    /* Above lastHandle: HANDLE_UNKNOWN, never by acting (CMP-034). */
    gsend(&r, e, b, bhms_enc_query(b, 9));
    expect_error(&r, BHMS_MSG_QUERY, 9, BHMS_E_HANDLE_UNKNOWN);
    CHECK(g.led_calls == 1);

    /* Gateway restart with a device reboot in between: new epoch is visible both in
     * HELLO and as the session of the refusal of an old-epoch QUERY. */
    rig_reboot(&r);
    gsend(&r, e, b, bhms_enc_query(b, 1));
    CHECK(next(&r, &f) == 1);
    bhms_error er;
    CHECK(bhms_dec_error(f.payload, f.length, &er) == 0 && er.code == BHMS_E_SESSION_MISMATCH);
    CHECK(f.session == 2);
    CHECK(hello(&r, 0, 7, &h) == 2 && h.last_handle == 0);
    gsend(&r, 2, b, bhms_enc_query(b, 1)); /* ring is empty after the reboot */
    expect_error(&r, BHMS_MSG_QUERY, 1, BHMS_E_HANDLE_UNKNOWN);
}

static void test_session_and_malformed(void) {
    rig r;
    bhms_hello h;
    uint8_t b[64];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);

    invoke(&r, 0, 1, 0, 0, 0, kOn, 1); /* session 0 only valid for HELLO_REQ */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_SESSION_MISMATCH);
    invoke(&r, e + 1, 1, 0, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_SESSION_MISMATCH);
    invoke(&r, e | (1ULL << 40), 1, 0, 0, 0, kOn, 1); /* upper epoch bits must match too */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_SESSION_MISMATCH);
    gsend(&r, 77, b, bhms_enc_read(b, 4, 0, 0));
    expect_error(&r, BHMS_MSG_READ, 4, BHMS_E_SESSION_MISMATCH);
    gsend(&r, 77, b, bhms_enc_cancel(b, 3));
    expect_error(&r, BHMS_MSG_CANCEL, 3, BHMS_E_SESSION_MISMATCH);
    CHECK(g.led_calls == 0);

    /* CMP-002: exact lengths. */
    size_t n = bhms_enc_cancel(b, 1);
    gsend(&r, e, b, n + 1);
    expect_error(&r, BHMS_MSG_CANCEL, 1, BHMS_E_MALFORMED);
    gsend(&r, e, b, n - 1);
    expect_error(&r, BHMS_MSG_CANCEL, 0, BHMS_E_MALFORMED);
    n = bhms_enc_hello_req(b, 0, 1);
    gsend(&r, 0, b, n - 1);
    expect_error(&r, BHMS_MSG_HELLO_REQ, 0xFFFFu, BHMS_E_MALFORMED);
    gsend(&r, e, b, 9); /* INVOKE shorter than the fixed part */
    b[0] = BHMS_MSG_INVOKE;
    gsend(&r, e, b, 9);
    /* (first call carried garbage type; both must answer MALFORMED) */
    {
        bhms_host_frame f;
        CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_ERROR);
        CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_ERROR);
        CHECK(f.payload[4] == BHMS_E_MALFORMED);
        CHECK(bhms_host_tx_pending(&r.host) == 0);
    }
    b[0] = 0x42; /* unknown type */
    gsend(&r, e, b, 4);
    expect_error(&r, 0x42, 0xFFFFu, BHMS_E_MALFORMED);
    gsend(&r, e, b, 0); /* empty payload */
    expect_error(&r, 0, 0, BHMS_E_MALFORMED);
    b[0] = BHMS_MSG_HELLO; /* an endpoint-to-gateway message sent to the endpoint */
    gsend(&r, e, b, 24);
    expect_error(&r, BHMS_MSG_HELLO, 0xFFFFu, BHMS_E_MALFORMED);

    /* CMP-001: wrong channel / wrong kind are discarded without effect or reply. */
    n = bhms_enc_hello_req(b, 0, 5);
    bhms_host_feed_frame(&r.host, BHMS_KIND_CONTROL, 2, 0, 0, b, n);
    bhms_host_feed_frame(&r.host, BHMS_KIND_STATUS, 1, 0, 0, b, n);
    bhms_host_feed_frame(&r.host, BHMS_KIND_TELEMETRY, 1, 0, 0, b, n);
    bhms_poll(&r.ep);
    CHECK(bhms_host_tx_pending(&r.host) == 0);

    invoke(&r, e, 0, 0, 0, 0, kOn, 1); /* handle 0 */
    expect_error(&r, BHMS_MSG_INVOKE, 0, BHMS_E_MALFORMED);
}

static void test_invoke_validation(void) {
    rig r;
    bhms_hello h;
    uint8_t a[8];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);

    invoke(&r, e, 1, 9, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_UNKNOWN_ACTION);
    invoke(&r, e, 1, 0, 0, 0, kOn2, 2); /* wrong argument length */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_MALFORMED);
    invoke(&r, e, 1, 0, 0, 0, 0, 0);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_MALFORMED);
    uint8_t two = 2;
    invoke(&r, e, 1, 0, 0, 0, &two, 1); /* bool byte 2 */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_MALFORMED);

    /* Argument limits: detail = argument index. f32 over limit. */
    memcpy(a, kMoveArgs, 7);
    float over = 200.5f;
    memcpy(a, &over, 4);
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_OUT_OF_RANGE);
    bhms_host_frame f;
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    CHECK(next(&r, &f) == 1 && f.payload[5] == 0); /* detail 0 */
    memcpy(a, kMoveArgs, 7);
    a[4] = 0; a[5] = 0; /* u16 speed 0 < 1 */
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    CHECK(next(&r, &f) == 1 && f.payload[4] == BHMS_E_OUT_OF_RANGE && f.payload[5] == 1);
    memcpy(a, kMoveArgs, 7);
    a[6] = 6; /* i8 6 > 5 */
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    CHECK(next(&r, &f) == 1 && f.payload[4] == BHMS_E_OUT_OF_RANGE && f.payload[5] == 2);
    memcpy(a, kMoveArgs, 7);
    a[6] = 0xFB; /* -5 ok */
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);
    CHECK(g.move_calls == 1);

    /* NaN/Inf never valid. Handles above were refused without consuming. */
    rig_boot(&r, 1, &kDev);
    e = hello(&r, 0, 1, &h);
    float nan = NAN;
    memcpy(a, kMoveArgs, 7);
    memcpy(a, &nan, 4);
    invoke(&r, e, 1, 1, 5, 0, a, 7);
    CHECK(next(&r, &f) == 1 && f.payload[4] == BHMS_E_OUT_OF_RANGE);
    CHECK(g.move_calls == 0);

    /* Handler rejection: ERROR, handle not consumed, nothing in the ring. */
    g.reject_error = BHMS_E_INHIBITED;
    invoke(&r, e, 1, 3, 0, 0, 0, 0);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_INHIBITED);
    g.reject_error = BHMS_E_HANDLE_UNKNOWN; /* callbacks may not forge protocol codes */
    invoke(&r, e, 1, 3, 0, 0, 0, 0);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_PRECONDITION);
    gsend(&r, e, a, bhms_enc_query(a, 1));
    expect_error(&r, BHMS_MSG_QUERY, 1, BHMS_E_HANDLE_UNKNOWN);

    /* Failed action: RESULT failed with the device fault. */
    invoke(&r, e, 1, 2, 0, 0, 0, 0);
    CHECK(next(&r, &f) == 1);
    static const uint8_t want[] = {0x83, 1, 0, BHMS_ST_FAILED, BHMS_EV_MEASURED, 7};
    CHECK(f.length == 6);
    CHECK_BYTES(f.payload, want, 6);
}

static void test_fences(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 0, 0, kMoveArgs, 7); /* lease-required action with fence 0 */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_LEASE_REQUIRED);
    invoke(&r, e, 1, 1, 100, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);
    invoke(&r, e, 2, 1, 99, 0, kMoveArgs, 7); /* below the floor */
    expect_error(&r, BHMS_MSG_INVOKE, 2, BHMS_E_FENCED);
    invoke(&r, e, 2, 0, 50, 0, kOn, 1); /* fence below floor on a non-lease action too */
    expect_error(&r, BHMS_MSG_INVOKE, 2, BHMS_E_FENCED);
    invoke(&r, e, 2, 0, 0, 0, kOn, 1); /* fence 0 allowed where no lease is required */
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
    invoke(&r, e, 3, 1, 100, 0, kMoveArgs, 7); /* equal to the floor is fine */
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);

    /* Without FENCING, fences are ignored. */
    rig_boot(&r, 0, &kDevNoStop);
    e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 0, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);
}

static void test_ttl(void) {
    rig r;
    bhms_hello h;
    uint8_t b[64], wire[HMS_FRAME_WIRE_MAX];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    size_t n = bhms_enc_invoke(b, 1, 0, 0, 20, kOn, 1);
    size_t w = bhms_frame_encode(wire, sizeof wire, 1, 1, e, 0, b, n);
    /* Frame trickles in: its first byte at t=100, the last at t=140 > 20 ms TTL. */
    r.host.now_ms = 100;
    bhms_host_feed(&r.host, wire, 5);
    bhms_poll(&r.ep);
    r.host.now_ms = 140;
    bhms_host_feed(&r.host, wire + 5, w - 5);
    bhms_poll(&r.ep);
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_EXPIRED);
    CHECK(g.led_calls == 0);
    /* Within the TTL it runs. */
    n = bhms_enc_invoke(b, 1, 0, 0, 50, kOn, 1);
    w = bhms_frame_encode(wire, sizeof wire, 1, 1, e, 1, b, n);
    r.host.now_ms = 200;
    bhms_host_feed(&r.host, wire, 5);
    bhms_poll(&r.ep);
    r.host.now_ms = 230;
    bhms_host_feed(&r.host, wire + 5, w - 5);
    bhms_poll(&r.ep);
    bhms_host_frame f;
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
    CHECK(g.led_calls == 1);
}

static void test_busy_and_async(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[16];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    static const uint8_t running[] = {0x82, 1, 0, BHMS_ST_RUNNING, 0, 255};
    CHECK(f.length == 6);
    CHECK_BYTES(f.payload, running, 6);
    invoke(&r, e, 2, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    invoke(&r, e, 3, 1, 10, 0, kMoveArgs, 7); /* BHMS_MAX_ACTIVE reached */
    expect_error(&r, BHMS_MSG_INVOKE, 3, BHMS_E_BUSY);
    CHECK(g.move_calls == 2);
    /* A short action cannot sneak past the active limit either. */
    invoke(&r, e, 3, 0, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 3, BHMS_E_BUSY);

    /* QUERY of a running op gives STATUS. */
    gsend(&r, e, b, bhms_enc_query(b, 1));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS && f.payload[3] == BHMS_ST_RUNNING);

    /* Progress and completion are unsolicited (kind 03). */
    CHECK(bhms_op_progress(&r.ep, 1, 40) == BHMS_OK);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[5] == 40);
    CHECK(bhms_op_progress(&r.ep, 1, 101) == BHMS_ERR_INVALID);
    CHECK(bhms_op_progress(&r.ep, 99, 1) == BHMS_ERR_NO_ENTRY);
    bhms_value res;
    res.u = 0x1234;
    CHECK(bhms_op_finish(&r.ep, 1, BHMS_ST_COMPLETED, BHMS_EV_MEASURED, 0, &res) == BHMS_OK);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY);
    static const uint8_t done[] = {0x83, 1, 0, BHMS_ST_COMPLETED, BHMS_EV_MEASURED, 0, 0x34, 0x12};
    CHECK(f.length == 8);
    CHECK_BYTES(f.payload, done, 8);
    CHECK(bhms_op_finish(&r.ep, 1, BHMS_ST_COMPLETED, 0, 0, &res) == BHMS_ERR_STATE);
    CHECK(bhms_op_finish(&r.ep, 1, 2, 0, 0, &res) == BHMS_ERR_INVALID);
    CHECK(bhms_op_finish(&r.ep, 2, BHMS_ST_COMPLETED, 0, 0, 0) == BHMS_ERR_INVALID);
    /* CMP-035: RESULT again on QUERY and on a retransmitted INVOKE. */
    gsend(&r, e, b, bhms_enc_query(b, 1));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.length == 8);
    invoke(&r, e, 1, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.length == 8);
    CHECK(g.move_calls == 2);
    /* The slot is free again; a refused-with-BUSY handle can be retried. */
    invoke(&r, e, 3, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
}

static void test_cancel(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[16];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    gsend(&r, e, b, bhms_enc_cancel(b, 1));
    expect_error(&r, BHMS_MSG_CANCEL, 1, BHMS_E_HANDLE_UNKNOWN);

    invoke(&r, e, 1, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    g.cancel_mode = BHMS_CANCEL_REFUSED;
    gsend(&r, e, b, bhms_enc_cancel(b, 1));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);
    CHECK(f.payload[3] == BHMS_ST_RUNNING && f.payload[4] == BHMS_CANCEL_REFUSED);
    g.cancel_mode = BHMS_CANCEL_ACK;
    gsend(&r, e, b, bhms_enc_cancel(b, 1));
    CHECK(next(&r, &f) == 1 && f.payload[4] == BHMS_CANCEL_ACK && f.payload[3] == BHMS_ST_RUNNING);
    CHECK(bhms_op_finish(&r.ep, 1, BHMS_ST_CANCELED, BHMS_EV_MEASURED, 0, 0) == BHMS_OK);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.payload[3] == BHMS_ST_CANCELED);

    invoke(&r, e, 2, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    g.cancel_mode = BHMS_CANCEL_CONFIRMED;
    gsend(&r, e, b, bhms_enc_cancel(b, 2));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.payload[3] == BHMS_ST_CANCELED);
    /* CANCEL of a terminal op: idempotent, answers the RESULT again. */
    gsend(&r, e, b, bhms_enc_cancel(b, 2));
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.payload[3] == BHMS_ST_CANCELED);

    /* An action with no cancel callback refuses. */
    invoke(&r, e, 3, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1);
}

static void test_read_and_publish(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[16];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    gsend(&r, e, b, bhms_enc_read(b, 0x0A0B, 0, BHMS_READ_FRESH));
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_STATUS);
    static const uint8_t v0[] = {0x84, 0x0B, 0x0A, 0, BHMS_Q_VALID, BHMS_VEV_MEASURED,
                                 1, 0, 0, 0, 5, 0, 0, 0, 0x55, 0x01};
    CHECK(f.length == sizeof v0);
    CHECK_BYTES(f.payload, v0, sizeof v0);
    CHECK(g.fresh_seen == 1);
    gsend(&r, e, b, bhms_enc_read(b, 1, 0, 0));
    CHECK(next(&r, &f) == 1 && g.fresh_seen == 0);
    bhms_valuemsg v;
    CHECK(bhms_dec_value(f.payload, f.length, &v) == 0 && v.sequence == 2);

    gsend(&r, e, b, bhms_enc_read(b, 2, 1, 0));
    CHECK(next(&r, &f) == 1);
    CHECK(bhms_dec_value(f.payload, f.length, &v) == 0 && v.n_value == 4);
    static const uint8_t f215[] = {0x00, 0x00, 0xAC, 0x41};
    CHECK_BYTES(v.value, f215, 4);

    /* CMP-060: invalid/unknown carries no value; stale keeps it. */
    g.quality = BHMS_Q_INVALID;
    gsend(&r, e, b, bhms_enc_read(b, 3, 0, 0));
    CHECK(next(&r, &f) == 1 && f.length == 14 && f.payload[4] == BHMS_Q_INVALID);
    g.quality = BHMS_Q_UNKNOWN;
    gsend(&r, e, b, bhms_enc_read(b, 3, 0, 0));
    CHECK(next(&r, &f) == 1 && f.length == 14 && f.payload[4] == BHMS_Q_UNKNOWN);
    g.quality = BHMS_Q_STALE;
    gsend(&r, e, b, bhms_enc_read(b, 3, 0, 0));
    CHECK(next(&r, &f) == 1 && f.length == 16 && f.payload[4] == BHMS_Q_STALE);
    g.quality = 9; /* callback returned garbage: reported as unknown */
    gsend(&r, e, b, bhms_enc_read(b, 3, 0, 0));
    CHECK(next(&r, &f) == 1 && f.length == 14 && f.payload[4] == BHMS_Q_UNKNOWN);
    g.quality = BHMS_Q_VALID;

    gsend(&r, e, b, bhms_enc_read(b, 8, 5, 0));
    expect_error(&r, BHMS_MSG_READ, 8, BHMS_E_UNKNOWN_PROPERTY);

    CHECK(bhms_publish(&r.ep, 0) == BHMS_OK);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY);
    CHECK(bhms_dec_value(f.payload, f.length, &v) == 0 && v.request == 0 && v.property == 0);
    CHECK(bhms_publish(&r.ep, 7) == BHMS_ERR_INVALID);
}

static void test_stop(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[16];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 400, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    invoke(&r, e, 2, 1, 412, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);

    /* STOP with a foreign session is still accepted (CMP-050), confirmed at once;
     * every active op is canceled; ack comes first, then the RESULTs. */
    gsend(&r, 12345, b, bhms_enc_stop(b, BHMS_STOP_OPERATOR));
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_STATUS);
    static const uint8_t ack[] = {0x85, BHMS_STOPACK_CONFIRMED, BHMS_EV_MEASURED, 2};
    CHECK(f.length == 4);
    CHECK_BYTES(f.payload, ack, 4);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[0] == BHMS_MSG_RESULT);
    CHECK(f.payload[3] == BHMS_ST_CANCELED);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[0] == BHMS_MSG_RESULT);
    CHECK(next(&r, &f) == 0);
    CHECK(g.stops == 1);
    /* CMP-051: fences seen are below the floor now (floor = 413). */
    invoke(&r, e, 3, 1, 412, 0, kMoveArgs, 7);
    expect_error(&r, BHMS_MSG_INVOKE, 3, BHMS_E_FENCED);
    invoke(&r, e, 3, 1, 413, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS);

    /* INITIATED then confirmed: a second ack (kind 03) when the app confirms. */
    g.stop_mode = BHMS_STOPACK_INITIATED;
    gsend(&r, e, b, bhms_enc_stop(b, BHMS_STOP_CLIENT));
    CHECK(next(&r, &f) == 1 && f.payload[1] == BHMS_STOPACK_INITIATED);
    CHECK(next(&r, &f) == 1); /* the canceled RESULT for handle 3 */
    bhms_stop_confirmed(&r.ep, BHMS_EV_MEASURED);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[1] == BHMS_STOPACK_CONFIRMED);
    CHECK(f.payload[3] == 1);
    bhms_stop_confirmed(&r.ep, BHMS_EV_MEASURED); /* only once */
    CHECK(next(&r, &f) == 0);

    /* No stop procedure: reported unsupported, ops still ended. */
    rig_boot(&r, 0, &kDevNoStop);
    e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 0, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    gsend(&r, e, b, bhms_enc_stop(b, 0));
    CHECK(next(&r, &f) == 1 && f.payload[1] == BHMS_STOPACK_UNSUPPORTED && f.payload[3] == 1);
}

static void test_stop_pin_and_inhibit(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 1, 7, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    r.host.pin = 1;
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[0] == BHMS_MSG_STOP_ACK);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && f.payload[3] == BHMS_ST_CANCELED);
    bhms_poll(&r.ep); /* level, not edge: no second stop */
    CHECK(next(&r, &f) == 0 && g.stops == 1);
    invoke(&r, e, 2, 0, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 2, BHMS_E_INHIBITED);
    r.host.pin = 0;
    bhms_poll(&r.ep);
    invoke(&r, e, 2, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);

    bhms_set_inhibit(&r.ep, 1);
    invoke(&r, e, 3, 0, 0, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 3, BHMS_E_INHIBITED);
    bhms_set_inhibit(&r.ep, 0);
    invoke(&r, e, 3, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
}

static void test_new_session(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    CHECK(next(&r, &f) == 1);
    invoke(&r, e, 2, 1, 50, 0, kMoveArgs, 7); /* active op */
    CHECK(next(&r, &f) == 1);

    /* CMP-023: ignored with an active operation; same epoch reported. */
    uint64_t e2 = hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 2, &h);
    CHECK(e2 == e && h.last_handle == 2);

    CHECK(bhms_op_finish(&r.ep, 2, BHMS_ST_FAILED, BHMS_EV_NONE, 3, 0) == BHMS_OK);
    CHECK(next(&r, &f) == 1);
    /* Now honoured: epoch +1 (persisted), ring cleared, lastHandle 0, fence floor 0. */
    e2 = hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 3, &h);
    CHECK(e2 == e + 1 && h.last_handle == 0 && r.host.eeprom == e2);
    CHECK(h.flags & BHMS_HELLO_PERSISTENT_EPOCH);
    invoke(&r, e, 1, 0, 0, 0, kOn, 1); /* old epoch refused */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_SESSION_MISMATCH);
    invoke(&r, e2, 1, 1, 5, 0, kMoveArgs, 7); /* handle 1 reusable, floor back at 0 */
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_STATUS && f.session == e2);
    CHECK(f.sequence == 2); /* counter restarted at the new-session HELLO (0), then the ERROR (1) */

    /* Non-persistent endpoint: NEW_SESSION still bumps the epoch in memory. */
    rig_boot(&r, 0, &kDev);
    e = hello(&r, 0, 1, &h);
    e2 = hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 2, &h);
    CHECK(e2 == e + 1 && (h.flags & BHMS_HELLO_PERSISTENT_EPOCH) == 0);
}

static void test_link_faults(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[64], wire[HMS_FRAME_WIRE_MAX];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);

    size_t n = bhms_enc_invoke(b, 1, 0, 0, 0, kOn, 1);
    size_t w = bhms_frame_encode(wire, sizeof wire, 1, 1, e, 0, b, n);
    /* Corrupt every byte position in turn: never an effect, never a crash. */
    for (size_t i = 1; i + 1 < w; ++i) {
        uint8_t bad[HMS_FRAME_WIRE_MAX];
        memcpy(bad, wire, w);
        bad[i] ^= 0x04;
        if (bad[i] == 0x7e) continue; /* would split the frame: covered elsewhere */
        bhms_host_feed(&r.host, bad, w);
        bhms_poll(&r.ep);
    }
    CHECK(g.led_calls == 0);
    CHECK(r.ep.bad_frames > 0);
    while (next(&r, &f) != 0) { /* any replies must be well-formed ERROR/none */ }
    /* The link recovers: next good frame is processed. */
    bhms_host_feed(&r.host, wire, w);
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && g.led_calls == 1);

    /* Garbage with no flags, then a long run overflowing the parser, then a frame. */
    uint8_t junk[300];
    memset(junk, 0x55, sizeof junk);
    bhms_host_feed(&r.host, (const uint8_t[]){0x7e}, 1);
    bhms_host_feed(&r.host, junk, sizeof junk);
    bhms_poll(&r.ep);
    bhms_poll(&r.ep);
    bhms_host_feed(&r.host, wire, w); /* retransmit of handle 1 answered from ring */
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT && g.led_calls == 1);

    /* Truncated frame, then silence: the absolute deadline discards the fragment. */
    bhms_host_feed(&r.host, wire, w / 2);
    bhms_poll(&r.ep);
    r.host.now_ms += BHMS_RX_TIMEOUT_MS + 5;
    bhms_poll(&r.ep);
    uint16_t bad = r.ep.bad_frames;
    CHECK(bad > 0);
    bhms_host_feed(&r.host, wire + w / 2, w - w / 2); /* tail without its head: no frame */
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 0);

    /* Oversize frame: payload of 192 bytes is a valid frame but a MALFORMED INVOKE. */
    uint8_t big[HMS_FRAME_PAYLOAD];
    memset(big, 0, sizeof big);
    big[0] = BHMS_MSG_INVOKE;
    big[1] = 9;
    gsend(&r, e, big, sizeof big);
    expect_error(&r, BHMS_MSG_INVOKE, 9, BHMS_E_MALFORMED);
    /* A frame bigger than the protocol maximum never reaches dispatch. */
    uint8_t huge[HMS_FRAME_WIRE_MAX + 8];
    size_t hw = bhms_frame_encode(huge, sizeof huge, 1, 1, e, 0, big, sizeof big);
    CHECK(hw > 0);
    memset(huge + 1 + 18, 0xFF, 1); /* header length field > 192 */
    bhms_host_feed(&r.host, huge, hw);
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 0);
}

static void test_poll_bounded(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[16];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    /* More queued frames than one poll consumes: later polls finish them. */
    size_t per = 0;
    for (int i = 0; i < 12; ++i) {
        size_t n = bhms_enc_query(b, (uint16_t)(100 + i));
        CHECK(bhms_host_feed_frame(&r.host, 1, 1, e, 0, b, n) == 0);
        per = r.host.rx_len / (size_t)(i + 1);
    }
    CHECK(per * 12 > BHMS_POLL_MAX_BYTES);
    bhms_poll(&r.ep);
    CHECK(r.host.rx_len > 0); /* bounded: not everything was consumed */
    int polls = 1;
    while (r.host.rx_len > 0 && polls < 100) { bhms_poll(&r.ep); ++polls; }
    int errs = 0;
    while (next(&r, &f) == 1) ++errs;
    CHECK(errs == 12);
}

static uint8_t big_run(void *u, const bhms_value *a, bhms_call *c) { (void)u; (void)a; (void)c; return 0; }
static void test_init_validation(void) {
    rig r;
    memset(&r, 0, sizeof r);
    bhms_host_init(&r.host, 0);
    BHMS_FIELDS(too_big) = {BHMS_U32(), BHMS_U32(), BHMS_U32(), BHMS_U32(), BHMS_U8()};
    static const bhms_action bad[] = {BHMS_ACTION(big_run, 0, 0, BHMS_FIELDS_REF(too_big), BHMS_NO_FIELDS)};
    bhms_device dev = {{0}, 0, bad, 1, 0, 0, 0, 0};
    CHECK(bhms_init(&r.ep, &dev, &r.host.hal) == BHMS_ERR_INVALID); /* 17 > BHMS_MAX_ARGS */
    BHMS_FIELDS(bad_type) = {{0, 0, 0, 0, 0.0f, 0.0f}};
    static const bhms_action bad2[] = {BHMS_ACTION(big_run, 0, 0, BHMS_FIELDS_REF(bad_type), BHMS_NO_FIELDS)};
    dev.actions = bad2;
    CHECK(bhms_init(&r.ep, &dev, &r.host.hal) == BHMS_ERR_INVALID);
    static const bhms_action nullrun[] = {BHMS_ACTION(0, 0, 0, BHMS_NO_FIELDS, BHMS_NO_FIELDS)};
    dev.actions = nullrun;
    CHECK(bhms_init(&r.ep, &dev, &r.host.hal) == BHMS_ERR_INVALID);
    dev.n_actions = 0;
    CHECK(bhms_init(&r.ep, &dev, &r.host.hal) == BHMS_OK); /* a device may have no actions */
    bhms_hal nohal = r.host.hal;
    nohal.millis = 0;
    CHECK(bhms_init(&r.ep, &dev, &nohal) == BHMS_ERR_INVALID);
    CHECK(bhms_init(0, &dev, &r.host.hal) == BHMS_ERR_INVALID);
}

static unsigned rnd(unsigned *seed) {
    *seed = *seed * 1664525u + 1013904223u;
    return *seed >> 8;
}

/* Property test: random frames and raw noise never crash the endpoint (ASan/UBSan
 * in CI), every reply it emits is a well-formed frame, handles never run twice,
 * and the ring invariants hold. */
static void test_random_input(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t payload[HMS_FRAME_PAYLOAD];
    unsigned seed = 7;
#define RND() rnd(&seed)
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    for (int iter = 0; iter < 20000; ++iter) {
        size_t n = RND() % 40;
        for (size_t i = 0; i < n; ++i) payload[i] = (uint8_t)RND();
        if (n > 0 && RND() % 4 != 0) payload[0] = (uint8_t)(1 + RND() % 6); /* mostly real types */
        if (n > 4 && RND() % 2) { payload[1] = (uint8_t)(RND() % 12); payload[2] = 0; }
        uint64_t session = RND() % 5 == 0 ? RND() : e;
        if (RND() % 11 == 0) {
            uint8_t noise[64];
            size_t m = RND() % 64;
            for (size_t i = 0; i < m; ++i) noise[i] = (uint8_t)RND();
            bhms_host_feed(&r.host, noise, m);
        } else {
            bhms_host_feed_frame(&r.host, (uint8_t)(RND() % 5 == 0 ? 2 : 1), (uint8_t)(RND() % 9 == 0 ? 2 : 1),
                                 session, (uint32_t)RND(), payload, n);
        }
        r.host.now_ms += RND() % 300;
        bhms_poll(&r.ep);
        if (RND() % 37 == 0 && r.ep.ring[0].stamp != 0) { /* finish whatever is running */
            for (uint16_t k = 1; k < 64; ++k) (void)bhms_op_finish(&r.ep, k, BHMS_ST_FAILED, 0, 1, 0);
        }
        if (r.host.tx_len > BHMS_HOST_TX_CAP / 2) { /* drain and validate replies */
            int rc;
            while ((rc = next(&r, &f)) != 0) {
                CHECK(rc == 1);
                CHECK(f.length >= 1 && f.channel == 1 && f.kind >= 2);
            }
            r.host.tx_len = r.host.tx_read = 0;
        }
        /* Invariants: handles unique among occupied entries, at most MAX_ACTIVE active. */
        unsigned active = 0;
        for (unsigned i = 0; i < BHMS_RING_SIZE; ++i) {
            const bhms_entry *a = &r.ep.ring[i];
            if (a->stamp == 0) continue;
            CHECK(a->handle != 0 && a->handle <= r.ep.last_handle);
            if (a->state == BHMS_ST_ACCEPTED || a->state == BHMS_ST_RUNNING) ++active;
            for (unsigned j = i + 1; j < BHMS_RING_SIZE; ++j)
                CHECK(r.ep.ring[j].stamp == 0 || r.ep.ring[j].handle != a->handle);
        }
        CHECK(active <= BHMS_MAX_ACTIVE);
        /* Keep the 16-bit handle space from running out. */
        if (r.ep.last_handle > 60000) {
            e = hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 9, &h);
            r.host.rx_len = 0;
        }
    }
#undef RND
}

/* I1: progress reported inside run followed by DONE must not wedge the slot. */
static void test_progress_inside_run(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    for (uint16_t hnd = 1; hnd <= 6; ++hnd) { /* more than BHMS_MAX_ACTIVE: no slot may leak */
        invoke(&r, e, hnd, 4, 0, 0, 0, 0);
        CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_TELEMETRY && f.payload[0] == BHMS_MSG_STATUS);
        CHECK(next(&r, &f) == 1 && f.kind == BHMS_KIND_STATUS && f.payload[0] == BHMS_MSG_RESULT);
        CHECK(f.payload[3] == BHMS_ST_COMPLETED);
    }
    for (unsigned i = 0; i < BHMS_RING_SIZE; ++i)
        CHECK(r.ep.ring[i].stamp == 0 || r.ep.ring[i].state == BHMS_ST_COMPLETED);
    hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 2, &h); /* honoured: nothing active */
    CHECK(h.epoch == e + 1);
}

/* I2: a failed init leaves an inert endpoint, never a live unsafe one. */
static void test_failed_init_is_inert(void) {
    rig r;
    uint8_t b[16];
    bhms_host_frame f;
    memset(&r, 0, sizeof r);
    bhms_host_init(&r.host, 0);
    BHMS_FIELDS(wide) = {BHMS_U32(), BHMS_U32(), BHMS_U32(), BHMS_U32(), BHMS_U32(), BHMS_U32(),
                         BHMS_U32(), BHMS_U32()}; /* 32 bytes > BHMS_MAX_ARGS */
    static const bhms_action acts[] = {
        BHMS_ACTION(led_run, 0, 0, BHMS_FIELDS_REF(wide), BHMS_NO_FIELDS)};
    bhms_device dev = {{0}, 0, acts, 1, 0, 0, 0, 0};
    CHECK(bhms_init(&r.ep, &dev, &r.host.hal) == BHMS_ERR_INVALID);
    CHECK(r.ep.dev == 0);
    bhms_host_feed_frame(&r.host, 1, 1, 0, 0, b, bhms_enc_hello_req(b, 0, 1));
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 0); /* silent: no HELLO with epoch 0 */
    uint8_t inv[64];
    size_t n = bhms_enc_invoke(inv, 1, 0, 0, 0, (const uint8_t[32]){0}, 32);
    bhms_host_feed_frame(&r.host, 1, 1, 0, 1, inv, n);
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 0 && g.led_calls == 0);
    CHECK(bhms_op_finish(&r.ep, 1, BHMS_ST_COMPLETED, 0, 0, 0) == BHMS_ERR_INVALID);
    CHECK(bhms_op_progress(&r.ep, 1, 1) == BHMS_ERR_INVALID);
    CHECK(bhms_publish(&r.ep, 0) == BHMS_ERR_INVALID);
    bhms_stop_confirmed(&r.ep, 0);
    bhms_set_inhibit(&r.ep, 1);
    CHECK(r.ep.inhibit == 0);
    /* A failing HAL check: poll must not dereference the missing hal. */
    memset(&r.ep, 0xA5, sizeof r.ep);
    r.ep.dev = 0;
    bhms_poll(&r.ep);
    bhms_hal bad = r.host.hal;
    bad.millis = 0;
    dev.n_actions = 0;
    CHECK(bhms_init(&r.ep, &dev, &bad) == BHMS_ERR_INVALID);
    bhms_poll(&r.ep);
    CHECK(next(&r, &f) == 0);
}

/* I3 + M6: a refused INVOKE still raises the fence floor; nothing else is consumed. */
static void test_fence_floor_on_refusal(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t a[8];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    memcpy(a, kMoveArgs, 7);
    float over = 500.0f;
    memcpy(a, &over, 4);
    invoke(&r, e, 1, 1, 5, 0, a, 7); /* fence 5, OUT_OF_RANGE */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_OUT_OF_RANGE);
    CHECK(r.ep.last_handle == 0 && r.ep.fence_floor == 5);
    invoke(&r, e, 1, 0, 4, 0, kOn, 1); /* older lease holder: fenced */
    expect_error(&r, BHMS_MSG_INVOKE, 1, BHMS_E_FENCED);
    invoke(&r, e, 1, 0, 5, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);

    /* BUSY refusal raises it too. */
    invoke(&r, e, 2, 1, 10, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    invoke(&r, e, 3, 1, 11, 0, kMoveArgs, 7);
    CHECK(next(&r, &f) == 1);
    invoke(&r, e, 4, 1, 12, 0, kMoveArgs, 7);
    expect_error(&r, BHMS_MSG_INVOKE, 4, BHMS_E_BUSY);
    CHECK(r.ep.fence_floor == 12);
    invoke(&r, e, 4, 0, 11, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 4, BHMS_E_FENCED);

    /* INHIBITED refusal raises it. */
    bhms_set_inhibit(&r.ep, 1);
    invoke(&r, e, 4, 0, 20, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 4, BHMS_E_INHIBITED);
    CHECK(r.ep.fence_floor == 20);
    bhms_set_inhibit(&r.ep, 0);

    /* EXPIRED refusal raises it. */
    uint8_t b[64], wire[HMS_FRAME_WIRE_MAX];
    size_t n = bhms_enc_invoke(b, 4, 0, 30, 10, kOn, 1);
    size_t w = bhms_frame_encode(wire, sizeof wire, 1, 1, e, 50, b, n);
    r.host.now_ms = 1000;
    bhms_host_feed(&r.host, wire, 5);
    bhms_poll(&r.ep);
    r.host.now_ms = 1100;
    bhms_host_feed(&r.host, wire + 5, w - 5);
    bhms_poll(&r.ep);
    expect_error(&r, BHMS_MSG_INVOKE, 4, BHMS_E_EXPIRED);
    CHECK(r.ep.fence_floor == 30);

    /* M6: frames refused before the fence check never move the fence state. */
    invoke(&r, e, 9, 9, 0xFFFFFFFFu, 0, kOn, 1); /* unknown action */
    expect_error(&r, BHMS_MSG_INVOKE, 9, BHMS_E_UNKNOWN_ACTION);
    invoke(&r, e, 9, 0, 0xFFFFFFFFu, 0, kOn2, 2); /* bad length */
    expect_error(&r, BHMS_MSG_INVOKE, 9, BHMS_E_MALFORMED);
    CHECK(r.ep.fence_floor == 30 && r.ep.max_fence == 30);
    CHECK(bhms_op_finish(&r.ep, 2, BHMS_ST_FAILED, 0, 1, 0) == BHMS_OK);
    CHECK(bhms_op_finish(&r.ep, 3, BHMS_ST_FAILED, 0, 1, 0) == BHMS_OK);
    CHECK(next(&r, &f) == 1 && next(&r, &f) == 1);
    invoke(&r, e, 4, 0, 31, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
}

/* M6: saturation is explicit. A STOP after fence 0xFFFFFFFF pins the floor there:
 * only that fence value (and no lower one) is admitted for the rest of the epoch. */
static void test_fence_saturation(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    uint8_t b[8];
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    invoke(&r, e, 1, 0, 0xFFFFFFFFu, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
    gsend(&r, e, b, bhms_enc_stop(b, 0));
    CHECK(next(&r, &f) == 1);
    CHECK(r.ep.fence_floor == 0xFFFFFFFFu);
    invoke(&r, e, 2, 0, 0xFFFFFFFEu, 0, kOn, 1);
    expect_error(&r, BHMS_MSG_INVOKE, 2, BHMS_E_FENCED);
    invoke(&r, e, 2, 0, 0xFFFFFFFFu, 0, kOn, 1);
    CHECK(next(&r, &f) == 1 && f.payload[0] == BHMS_MSG_RESULT);
}

/* I4: an unreadable boot counter must not be reported as persistent. */
static void test_load_failure_not_persistent(void) {
    rig r;
    bhms_hello h;
    rig_boot(&r, 1, &kDev);
    r.host.eeprom = 77;
    r.host.eeprom_writes = 0;
    r.host.load_fails = 1;
    CHECK(bhms_init(&r.ep, &kDev, &r.host.hal) == BHMS_OK);
    hello(&r, 0, 1, &h);
    CHECK(h.epoch == 1 && (h.flags & BHMS_HELLO_PERSISTENT_EPOCH) == 0);
    CHECK(r.host.eeprom == 77 && r.host.eeprom_writes == 0); /* nothing stored over the cell */
    hello(&r, BHMS_HELLO_REQ_NEW_SESSION, 2, &h); /* stays non-persistent after NEW_SESSION */
    CHECK(h.epoch == 2 && (h.flags & BHMS_HELLO_PERSISTENT_EPOCH) == 0);
    CHECK(r.ep.stamp_clock == 0); /* M9 */
}

/* Frame sizes against the 64-byte budget (spec 11.3). */
static void test_wire_budget(void) {
    rig r;
    bhms_hello h;
    bhms_host_frame f;
    rig_boot(&r, 1, &kDev);
    uint64_t e = hello(&r, 0, 1, &h);
    size_t total_before = r.host.tx_len;
    invoke(&r, e, 1, 0, 0, 0, kOn, 1);
    size_t wire_len = r.host.tx_len - total_before;
    CHECK(wire_len == 24 + 7); /* RESULT with one byte: no padding */
    CHECK(next(&r, &f) == 1);
    CHECK(total_before == 24 + 24); /* HELLO frame: 48 bytes on the wire */
}

#define RUN(t) do { const char *only_ = getenv("BHMS_T_ONLY"); if (only_ != NULL && strcmp(only_, #t) != 0) break; if (getenv("BHMS_T_VERBOSE")) fprintf(stderr, "== %s\n", #t); t(); } while (0)

int main(void) {
    RUN(test_hello_and_epoch);
    RUN(test_persistent_epoch);
    RUN(test_invoke_result_exact);
    RUN(test_replay_ring);
    RUN(test_query_and_epoch_in_replies);
    RUN(test_session_and_malformed);
    RUN(test_invoke_validation);
    RUN(test_fences);
    RUN(test_ttl);
    RUN(test_busy_and_async);
    RUN(test_cancel);
    RUN(test_read_and_publish);
    RUN(test_stop);
    RUN(test_stop_pin_and_inhibit);
    RUN(test_new_session);
    RUN(test_link_faults);
    RUN(test_poll_bounded);
    RUN(test_init_validation);
    RUN(test_progress_inside_run);
    RUN(test_failed_init_is_inert);
    RUN(test_fence_floor_on_refusal);
    RUN(test_fence_saturation);
    RUN(test_load_failure_not_persistent);
    RUN(test_random_input);
    RUN(test_wire_budget);
    TEST_FINISH("test_endpoint");
}
