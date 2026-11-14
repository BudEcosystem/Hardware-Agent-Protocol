/* The BHMS device binding: the real compact endpoint over the in-memory HAL, bound to the arm
 * core and the simulated rig. A scripted gateway sends INVOKE/READ/STOP frames and parses every
 * reply with the reused C frame parser. */
#include <math.h>
#include <stdlib.h>

#include "arm_device.h"
#include "bhms_hal_host.h"
#include "bhms_test.h"
#include "sim_rig.h"
#include "arm_digest.h"

static const uint8_t kDigest[8] = BHMS_DIGEST8;

typedef struct {
    sim_rig rig;
    arm a;
    arm_device dev;
    bhms_host host;
    bhms_hal hal;
    uint32_t gseq;
    uint64_t epoch;
} board;

static sim_rig *g_rig;
static int pin_hook(void *c) {
    int v = g_rig->estop_pressed || g_rig->edge_bhms;
    (void)c;
    g_rig->edge_bhms = 0;
    return v;
}

static void boot(board *b) {
    memset(b, 0, sizeof *b);
    sim_rig_init(&b->rig);
    g_rig = &b->rig;
    bhms_host_init(&b->host, 1);
    b->hal = b->host.hal;
    b->hal.stop_pin = pin_hook;
    {
        arm_cal cal;
        arm_cal_nominal(&cal);
        arm_init(&b->a, &b->rig.hw, &cal, 0);
    }
    CHECK(arm_device_init(&b->dev, &b->a, &b->hal) == BHMS_OK);
}

static void pump(board *b, uint32_t ms) {
    uint32_t k;
    for (k = 0; k < ms; ++k) {
        sim_rig_advance(&b->rig, 1);
        ++b->host.now_ms;
        arm_device_poll(&b->dev);
    }
}

static void send(board *b, const uint8_t *payload, size_t n) {
    CHECK(bhms_host_feed_frame(&b->host, BHMS_KIND_CONTROL, BHMS_CHANNEL, b->epoch, b->gseq++, payload, n) == 0);
    pump(b, 2);
}

/* Drain the frames the device sent into `out`; returns the count. */
static int drain(board *b, bhms_host_frame *out, int cap) {
    int n = 0;
    while (n < cap && bhms_host_next_tx(&b->host, &out[n]) == 1) ++n;
    return n;
}

static const bhms_host_frame *find(const bhms_host_frame *f, int n, uint8_t type) {
    int i;
    for (i = 0; i < n; ++i)
        if (f[i].payload[0] == type) return &f[i];
    return 0;
}

/* A frame the test needs: a missing one is a failure that ends the test (never silently skipped). */
static const bhms_host_frame *must(const bhms_host_frame *f, const char *what) {
    if (f == 0) {
        fprintf(stderr, "FAIL missing frame: %s\n", what);
        exit(1);
    }
    return f;
}

static void say_hello(board *b, bhms_hello *h) {
    uint8_t p[16];
    bhms_host_frame f[4];
    CHECK(bhms_host_feed_frame(&b->host, BHMS_KIND_CONTROL, BHMS_CHANNEL, 0, b->gseq++, p,
                               bhms_enc_hello_req(p, 0, 0x1234)) == 0);
    pump(b, 2);
    CHECK(drain(b, f, 4) == 1 && bhms_dec_hello(f[0].payload, f[0].length, h) == 0);
    b->epoch = h->epoch;
}

static uint16_t g_handle;
static void invoke(board *b, uint8_t action, uint32_t fence, const uint8_t *args, size_t n) {
    uint8_t p[64];
    send(b, p, bhms_enc_invoke(p, ++g_handle, action, fence, 0, args, n));
}

static void put_i16(uint8_t *p, int v) { p[0] = (uint8_t)(v & 0xFF); p[1] = (uint8_t)((v >> 8) & 0xFF); }

static size_t move_args(uint8_t *a, double yaw, double sh, double el, double wr, double roll, int pct) {
    put_i16(a, (int)lround(yaw * 100));
    put_i16(a + 2, (int)lround(sh * 100));
    put_i16(a + 4, (int)lround(el * 100));
    put_i16(a + 6, (int)lround(wr * 100));
    put_i16(a + 8, (int)lround(roll * 100));
    a[10] = (uint8_t)pct;
    return 11;
}

static void expect_error(board *b, uint8_t code, int detail) {
    bhms_host_frame f[6];
    int n = drain(b, f, 6);
    const bhms_host_frame *e = find(f, n, BHMS_MSG_ERROR);
    bhms_error er;
    e = must(e, "ERROR");
    CHECK(bhms_dec_error(e->payload, e->length, &er) == 0);
    CHECK(er.code == code);
    if (detail >= 0) {
        if (er.detail != (uint8_t)detail) fprintf(stderr, "detail %u want %d code %u\n", er.detail, detail, er.code);
        CHECK(er.detail == (uint8_t)detail);
    }
}

static int read_prop(board *b, uint8_t prop, bhms_valuemsg *out) {
    uint8_t p[8];
    static bhms_host_frame f[8]; /* `out` points into the payload: keep it alive */
    const bhms_host_frame *v;
    int n;
    (void)drain(b, f, 8); /* anything still pending from earlier operations */
    send(b, p, bhms_enc_read(p, 7, prop, 0));
    n = drain(b, f, 8);
    v = find(f, n, BHMS_MSG_VALUE);
    return v != 0 && bhms_dec_value(v->payload, v->length, out) == 0;
}

static float value_f32(const bhms_valuemsg *v) {
    float x;
    memcpy(&x, v->value, 4);
    return x;
}

static void bring_up(board *b) {
    bhms_hello h;
    bhms_host_frame f[8];
    int n;
    const bhms_host_frame *r;
    bhms_result res;
    boot(b);
    say_hello(b, &h);
    invoke(b, ARM_ACT_ENABLE, 1, 0, 0);
    pump(b, 3000);
    n = drain(b, f, 8);
    r = find(f, n, BHMS_MSG_RESULT);
    r = must(r, "RESULT of enable");
    CHECK(bhms_dec_result(r->payload, r->length, &res) == 0);
    CHECK(res.state == BHMS_ST_COMPLETED && res.evidence == BHMS_EV_MEASURED);
    CHECK(b->a.state == ARM_ST_READY);
}

static void test_hello_and_tables(void) {
    board b;
    bhms_hello h;
    boot(&b);
    say_hello(&b, &h);
    CHECK(h.flags == (BHMS_HELLO_FENCING | BHMS_HELLO_STOP_SUPPORTED | BHMS_HELLO_PERSISTENT_EPOCH));
    CHECK_BYTES(h.digest8, kDigest, 8);
    CHECK(h.epoch == 1 && h.max_args == 11);
    CHECK(ARM_ACT_COUNT == b.dev.dev.n_actions && ARM_PROP_COUNT == b.dev.dev.n_properties);
    /* The flash-backed epoch advances at each boot. */
    {
        uint32_t cell = b.host.eeprom;
        boot(&b);
        b.host.eeprom = cell;
    }
}

static void test_leases_and_refusals(void) {
    board b;
    bhms_hello h;
    uint8_t a[16];
    boot(&b);
    say_hello(&b, &h);
    /* Every motion/power action needs a lease; hold does not. */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 0, a, move_args(a, 0, 30, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_LEASE_REQUIRED, -1);
    invoke(&b, ARM_ACT_RELEASE_TORQUE, 0, 0, 0);
    expect_error(&b, BHMS_E_LEASE_REQUIRED, -1);
    invoke(&b, ARM_ACT_ENABLE, 0, 0, 0);
    expect_error(&b, BHMS_E_LEASE_REQUIRED, -1);
    /* Not enabled yet: a valid move is a precondition failure naming the reason. */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 2, a, move_args(a, 0, 30, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_PRECONDITION, ARM_WHY_NOT_ENABLED);
}

static void test_limits_over_the_wire(void) {
    board b;
    bhms_host_frame f[8];
    uint8_t a[16];
    int n;
    bring_up(&b);
    /* The compact layout's own bounds catch a joint beyond its range (detail = field index). */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 3, a, move_args(a, 0, 96, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_OUT_OF_RANGE, 1);
    /* Coupled-limit violations pass the per-field ranges and are refused by the device itself,
     * naming the limit: 0x10 forearm_pitch, 0x11 hairpin, 0x12 tool_pitch. */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 3, a, move_args(a, 0, 80, 100, 0, 0, 50));
    expect_error(&b, BHMS_E_OUT_OF_RANGE, 0x10);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 3, a, move_args(a, 0, 0, 100, 70, 0, 50));
    expect_error(&b, BHMS_E_OUT_OF_RANGE, 0x11);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 3, a, move_args(a, 0, 50, 40, 95, 0, 50));
    expect_error(&b, BHMS_E_OUT_OF_RANGE, 0x12);
    /* None of them moved anything; a valid move is accepted and completes, measured. */
    CHECK(b.a.op == ARM_OP_NONE);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 3, a, move_args(a, 30, 40, 60, 10, -20, 80));
    n = drain(&b, f, 8);
    CHECK(n >= 1 && f[0].payload[0] == BHMS_MSG_STATUS);
    pump(&b, 8000);
    n = drain(&b, f, 8);
    {
        const bhms_host_frame *r = find(f, n, BHMS_MSG_RESULT);
        bhms_result res;
        r = must(r, "RESULT of move_joints");
        CHECK(bhms_dec_result(r->payload, r->length, &res) == 0);
        CHECK(res.state == BHMS_ST_COMPLETED && res.evidence == BHMS_EV_MEASURED && res.n_fields == 2);
    }
    {
        bhms_valuemsg v;
        CHECK(read_prop(&b, ARM_PROP_POSITION + ARM_J_BASE_YAW, &v) && v.quality == BHMS_Q_VALID);
        CHECK(v.evidence == BHMS_VEV_MEASURED && fabsf(value_f32(&v) - 30.0f) < 2.0f);
        CHECK(read_prop(&b, ARM_PROP_POSITION + ARM_J_SHOULDER, &v) && fabsf(value_f32(&v) - 40.0f) < 2.0f);
    }
}

static void test_estop_over_the_wire(void) {
    board b;
    bhms_host_frame f[10];
    uint8_t a[16];
    int n;
    bhms_valuemsg v;
    bring_up(&b);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 4, a, move_args(a, 100, 60, 80, 30, 50, 30));
    drain(&b, f, 10);
    pump(&b, 300);
    CHECK(b.a.state == ARM_ST_MOVING);
    sim_rig_press_estop(&b.rig, 1);
    pump(&b, 3);
    n = drain(&b, f, 10);
    {
        /* The pin path: the endpoint sees the edge, cancels the operation and acknowledges the stop;
         * the arm reports it as the E-stop. */
        const bhms_host_frame *ack = find(f, n, BHMS_MSG_STOP_ACK);
        bhms_stop_ack sa;
        ack = must(ack, "STOP_ACK on the pin edge");
        CHECK(ack->kind == BHMS_KIND_TELEMETRY);
        CHECK(bhms_dec_stop_ack(ack->payload, ack->length, &sa) == 0 && sa.canceled == 1);
        CHECK(sa.token == 0); /* the pin edge: never mistaken for a gateway's stop */
        CHECK(find(f, n, BHMS_MSG_RESULT) != 0 || find(f, n, BHMS_MSG_STATUS) != 0);
    }
    CHECK(b.a.state == ARM_ST_ESTOP && !b.rig.servo_en_pin);
    pump(&b, 100); /* rail measured dead: the second STOP_ACK (confirmed) follows */
    n = drain(&b, f, 10);
    {
        const bhms_host_frame *ack = find(f, n, BHMS_MSG_STOP_ACK);
        bhms_stop_ack sa;
        ack = must(ack, "second STOP_ACK (confirmed) after the E-stop");
        CHECK(bhms_dec_stop_ack(ack->payload, ack->length, &sa) == 0);
        CHECK(sa.outcome == BHMS_STOPACK_CONFIRMED && sa.evidence == BHMS_EV_MEASURED && sa.token == 0);
    }
    /* The E-stop is observable as a measured property, with the latch. */
    CHECK(read_prop(&b, ARM_PROP_ESTOP_STATE, &v) && v.quality == BHMS_Q_VALID && v.value[0] == ESTOP_PRESSED);
    CHECK(v.evidence == BHMS_VEV_MEASURED);
    CHECK(read_prop(&b, ARM_PROP_ESTOP_CONTACT, &v) && v.value[0] == 1);
    CHECK(read_prop(&b, ARM_PROP_ESTOP_LATCHED, &v) && v.value[0] == 1);
    CHECK(read_prop(&b, ARM_PROP_RAIL_MV, &v) && v.value[0] == 0 && v.value[1] == 0);
    /* Servo-derived properties are unknown while unpowered: no substituted value (CMP-060). */
    {
        uint8_t p[8];
        send(&b, p, bhms_enc_read(p, 9, ARM_PROP_POSITION, 0));
        n = drain(&b, f, 4);
        CHECK(n >= 1 && bhms_dec_value(f[0].payload, f[0].length, &v) == 0 && v.quality == BHMS_Q_UNKNOWN && v.n_value == 0);
    }
    /* While pressed, INVOKE is refused by the endpoint; released but latched, by the arm. */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 5, a, move_args(a, 0, 30, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_INHIBITED, -1);
    sim_rig_press_estop(&b.rig, 0);
    pump(&b, 5);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 6, a, move_args(a, 0, 30, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_INHIBITED, ARM_WHY_ESTOP_LATCHED);
    CHECK(!b.rig.servo_en_pin);
    /* Explicit enable (with a newer lease) recovers. */
    invoke(&b, ARM_ACT_ENABLE, 7, 0, 0);
    pump(&b, 3000);
    CHECK(b.a.state == ARM_ST_READY);
    CHECK(read_prop(&b, ARM_PROP_POSE_UNKNOWN, &v) && v.value[0] == 0);
}

static void test_stop_message_and_hold(void) {
    board b;
    bhms_host_frame f[10];
    uint8_t a[16], p[8];
    int n;
    bring_up(&b);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 8, a, move_args(a, -100, 60, 80, 30, 50, 30));
    drain(&b, f, 10);
    pump(&b, 300);
    send(&b, p, bhms_enc_stop(p, BHMS_STOP_CLIENT, 0x2B));
    n = drain(&b, f, 10);
    {
        const bhms_host_frame *ack = find(f, n, BHMS_MSG_STOP_ACK);
        bhms_stop_ack sa;
        ack = must(ack, "STOP_ACK (initiated)");
        CHECK(bhms_dec_stop_ack(ack->payload, ack->length, &sa) == 0);
        CHECK(sa.outcome == BHMS_STOPACK_INITIATED && sa.canceled == 1 && sa.token == 0x2B);
    }
    pump(&b, 800);
    n = drain(&b, f, 10);
    {
        const bhms_host_frame *ack = find(f, n, BHMS_MSG_STOP_ACK);
        bhms_stop_ack sa;
        ack = must(ack, "STOP_ACK (confirmed)");
        CHECK(bhms_dec_stop_ack(ack->payload, ack->length, &sa) == 0);
        CHECK(sa.outcome == BHMS_STOPACK_CONFIRMED && sa.evidence == BHMS_EV_MEASURED && sa.token == 0x2B);
    }
    /* The device fenced everything seen so far: the old lease is stale, a new one works. */
    invoke(&b, ARM_ACT_MOVE_JOINTS, 8, a, move_args(a, 0, 30, 90, 45, 0, 50));
    expect_error(&b, BHMS_E_FENCED, -1);
    invoke(&b, ARM_ACT_MOVE_JOINTS, 9, a, move_args(a, 0, 30, 90, 45, 0, 50));
    n = drain(&b, f, 10);
    CHECK(n >= 1 && f[0].payload[0] == BHMS_MSG_STATUS);
    /* hold (no lease needed) cancels the running move. */
    pump(&b, 100);
    invoke(&b, ARM_ACT_HOLD, 0, 0, 0);
    n = drain(&b, f, 10);
    CHECK(find(f, n, BHMS_MSG_RESULT) != 0);
}

int main(void) {
    test_hello_and_tables();
    test_leases_and_refusals();
    test_limits_over_the_wire();
    test_estop_over_the_wire();
    test_stop_message_and_hold();
    TEST_FINISH("test_device");
}
