/* Byte-exact codec tests: spec/bhms/11-compact-binding.md 11.2 layouts and the
 * 11.10 worked vectors (produced with protocol/serial/frame.py). */
#include <stdlib.h>

#include "bhms.h"
#include "bhms_test.h"

static const uint8_t kInvokePayload[14] = {0x02, 0x11, 0x00, 0x00, 0x9c, 0x01, 0x00,
                                           0x00, 0x00, 0x00, 0xf4, 0x01, 0x64, 0x00};
static const uint8_t kInvokeFrame[38] = {
    0x7e, 0x48, 0x4d, 0x01, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x29,
    0x00, 0x00, 0x00, 0x07, 0x00, 0x0e, 0x02, 0x11, 0x00, 0x00, 0x9c, 0x01, 0x00, 0x00, 0x00,
    0x00, 0xf4, 0x01, 0x64, 0x00, 0xe5, 0xf9, 0x7e};
static const uint8_t kResultPayload[8] = {0x83, 0x11, 0x00, 0x03, 0x02, 0x00, 0xf5, 0x01};
static const uint8_t kResultFrame[32] = {
    0x7e, 0x48, 0x4d, 0x01, 0x02, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x29, 0x00,
    0x00, 0x00, 0x09, 0x00, 0x08, 0x83, 0x11, 0x00, 0x03, 0x02, 0x00, 0xf5, 0x01, 0x33, 0x22, 0x7e};

static void test_spec_vectors(void) {
    uint8_t buf[64], wire[HMS_FRAME_WIRE_MAX];
    size_t n = bhms_enc_invoke(buf, 17, 0, 412, 0, (const uint8_t[]){0xf4, 0x01, 0x64, 0x00}, 4);
    CHECK(n == sizeof kInvokePayload);
    CHECK_BYTES(buf, kInvokePayload, n);
    n = bhms_frame_encode(wire, sizeof wire, BHMS_KIND_CONTROL, BHMS_CHANNEL, 41, 7, buf, 14);
    CHECK(n == sizeof kInvokeFrame);
    CHECK_BYTES(wire, kInvokeFrame, sizeof kInvokeFrame);

    n = bhms_enc_result(buf, 17, BHMS_ST_COMPLETED, BHMS_EV_MEASURED, 0,
                        (const uint8_t[]){0xf5, 0x01}, 2);
    CHECK(n == sizeof kResultPayload);
    CHECK_BYTES(buf, kResultPayload, n);
    n = bhms_frame_encode(wire, sizeof wire, BHMS_KIND_STATUS, BHMS_CHANNEL, 41, 9, buf, 8);
    CHECK(n == sizeof kResultFrame);
    CHECK_BYTES(wire, kResultFrame, sizeof kResultFrame);

    /* The reused parser accepts exactly these bytes. */
    hms_frame_parser p;
    hms_frame_reset(&p);
    hms_frame_result r = HMS_FRAME_NONE;
    for (size_t i = 0; i < sizeof kInvokeFrame; ++i) r = hms_frame_feed(&p, kInvokeFrame[i]);
    CHECK(r == HMS_FRAME_READY);
    CHECK(p.raw[HMS_FRAME_HEADER] == 0x02);
}

static void test_message_layouts(void) {
    uint8_t b[64];
    static const uint8_t digest[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    size_t n;

    n = bhms_enc_hello_req(b, BHMS_HELLO_REQ_NEW_SESSION, 0xA1B2C3D4u);
    static const uint8_t hr[] = {0x01, 0x02, 0x01, 0xD4, 0xC3, 0xB2, 0xA1};
    CHECK(n == 7);
    CHECK_BYTES(b, hr, 7);

    n = bhms_enc_hello(b, 0x07, digest, 41, 0xA1B2C3D4u, 17, 4, 2, 16);
    static const uint8_t h[] = {0x81, 0x02, 0x07, 1, 2, 3, 4, 5, 6, 7, 8, 41, 0, 0, 0,
                                0xD4, 0xC3, 0xB2, 0xA1, 17, 0, 4, 2, 16};
    CHECK(n == 24);
    CHECK_BYTES(b, h, 24);

    n = bhms_enc_cancel(b, 0x1234);
    static const uint8_t c[] = {0x03, 0x34, 0x12};
    CHECK(n == 3);
    CHECK_BYTES(b, c, 3);

    n = bhms_enc_query(b, 0x1234);
    static const uint8_t q[] = {0x06, 0x34, 0x12};
    CHECK(n == 3);
    CHECK_BYTES(b, q, 3);

    n = bhms_enc_read(b, 0x0102, 3, BHMS_READ_FRESH);
    static const uint8_t rd[] = {0x04, 0x02, 0x01, 0x03, 0x01};
    CHECK(n == 5);
    CHECK_BYTES(b, rd, 5);

    n = bhms_enc_stop(b, BHMS_STOP_GATEWAY, 0x2A);
    static const uint8_t st[] = {0x05, 0x03, 0x2A};
    CHECK(n == 3);
    CHECK_BYTES(b, st, 3);

    n = bhms_enc_status(b, 17, BHMS_ST_RUNNING, BHMS_CANCEL_REQUESTED, 50);
    static const uint8_t ss[] = {0x82, 0x11, 0x00, 0x02, 0x01, 50};
    CHECK(n == 6);
    CHECK_BYTES(b, ss, 6);

    n = bhms_enc_value(b, 0, 1, BHMS_Q_VALID, BHMS_VEV_MEASURED, 0x01020304u, 0xFFFFFFFFu,
                       (const uint8_t[]){0x55, 0x01}, 2);
    static const uint8_t v[] = {0x84, 0, 0, 1, 0, 0, 4, 3, 2, 1, 0xFF, 0xFF, 0xFF, 0xFF, 0x55, 0x01};
    CHECK(n == 16);
    CHECK_BYTES(b, v, 16);

    n = bhms_enc_stop_ack(b, BHMS_STOPACK_CONFIRMED, BHMS_EV_MEASURED, 3, 0x2A);
    static const uint8_t sa[] = {0x85, 1, 2, 3, 0x2A};
    CHECK(n == 5);
    CHECK_BYTES(b, sa, 5);

    n = bhms_enc_error(b, BHMS_MSG_INVOKE, 0x0011, BHMS_E_OUT_OF_RANGE, 1);
    static const uint8_t e[] = {0xFF, 0x02, 0x11, 0x00, 4, 1};
    CHECK(n == 6);
    CHECK_BYTES(b, e, 6);
}

static void test_decoders(void) {
    bhms_hello_req hr;
    bhms_hello h;
    bhms_invoke inv;
    bhms_status s;
    bhms_result r;
    bhms_valuemsg v;
    bhms_stop_ack sa;
    bhms_error e;
    CHECK(bhms_dec_invoke(kInvokePayload, 14, &inv) == 0);
    CHECK(inv.handle == 17 && inv.action == 0 && inv.fence == 412 && inv.ttl_ms == 0);
    CHECK(inv.n_args == 4 && inv.args[0] == 0xf4);
    CHECK(bhms_dec_invoke(kInvokePayload, 9, &inv) == -1);
    CHECK(bhms_dec_result(kResultPayload, 8, &r) == 0);
    CHECK(r.handle == 17 && r.state == 3 && r.evidence == 2 && r.n_fields == 2);

    uint8_t b[32];
    size_t n = bhms_enc_hello_req(b, 0, 99);
    CHECK(bhms_dec_hello_req(b, n, &hr) == 0 && hr.nonce == 99 && hr.version == 2);
    CHECK(bhms_dec_hello_req(b, n - 1, &hr) == -1);
    n = bhms_enc_hello(b, 3, (const uint8_t[8]){9, 9, 9, 9, 9, 9, 9, 9}, 7, 8, 9, 4, 1, 12);
    CHECK(bhms_dec_hello(b, n, &h) == 0 && h.epoch == 7 && h.nonce == 8 && h.last_handle == 9);
    CHECK(h.ring == 4 && h.max_active == 1 && h.max_args == 12 && h.digest8[7] == 9);
    CHECK(bhms_dec_hello(b, n + 1, &h) == -1);
    n = bhms_enc_status(b, 5, 3, 0, 255);
    CHECK(bhms_dec_status(b, n, &s) == 0 && s.handle == 5 && s.progress == 255);
    n = bhms_enc_value(b, 4, 2, 0, 0, 10, 20, (const uint8_t[]){1, 2, 3, 4}, 4);
    CHECK(bhms_dec_value(b, n, &v) == 0 && v.request == 4 && v.sequence == 10 && v.n_value == 4);
    n = bhms_enc_stop_ack(b, 0, 0, 0, 77);
    CHECK(bhms_dec_stop_ack(b, n, &sa) == 0 && sa.outcome == 0 && sa.token == 77);
    CHECK(bhms_dec_stop_ack(b, n - 1, &sa) == -1); /* a version 1 (4 byte) ack is not accepted */
    n = bhms_enc_error(b, 4, 77, 3, 0);
    CHECK(bhms_dec_error(b, n, &e) == 0 && e.id == 77 && e.code == 3 && e.request_type == 4);
    b[0] = 0x00;
    CHECK(bhms_dec_error(b, 6, &e) == -1); /* wrong type byte */
}

static void test_values(void) {
    uint8_t b[4];
    bhms_value v, out;
    v.i = -2;
    bhms_value_put(BHMS_I16, v, b);
    CHECK(b[0] == 0xFE && b[1] == 0xFF);
    CHECK(bhms_value_get(BHMS_I16, b, &out) == 0 && out.i == -2);
    v.u = 0x80000001u;
    bhms_value_put(BHMS_U32, v, b);
    CHECK(b[0] == 1 && b[3] == 0x80);
    CHECK(bhms_value_get(BHMS_U32, b, &out) == 0 && out.u == 0x80000001u);
    v.f = 1.5f; /* 0x3FC00000 */
    bhms_value_put(BHMS_F32, v, b);
    static const uint8_t f15[] = {0x00, 0x00, 0xC0, 0x3F};
    CHECK_BYTES(b, f15, 4);
    CHECK(bhms_value_get(BHMS_F32, b, &out) == 0 && out.f == 1.5f);
    b[0] = 2;
    CHECK(bhms_value_get(BHMS_BOOL, b, &out) == -1);
    b[0] = 1;
    CHECK(bhms_value_get(BHMS_BOOL, b, &out) == 0 && out.u == 1);
    b[0] = 0x80;
    CHECK(bhms_value_get(BHMS_I8, b, &out) == 0 && out.i == -128);
    CHECK(bhms_value_get(0, b, &out) == -1);
    CHECK(bhms_type_width(BHMS_F32) == 4 && bhms_type_width(BHMS_BOOL) == 1 && bhms_type_width(9) == 0);
}

/* CMP-003: wire length is exactly 24 + payload + stuffed octets; every frame the
 * encoder emits must round-trip through the reused C parser. */
static void test_stuffing_roundtrip(void) {
    uint8_t payload[HMS_FRAME_PAYLOAD], wire[HMS_FRAME_WIRE_MAX];
    srand(12345);
    for (int iter = 0; iter < 400; ++iter) {
        size_t n = (size_t)(rand() % (HMS_FRAME_PAYLOAD + 1));
        for (size_t i = 0; i < n; ++i) {
            int pick = rand() % 6;
            payload[i] = pick == 0 ? 0x7e : pick == 1 ? 0x7d : (uint8_t)rand();
        }
        uint32_t seq = (uint32_t)rand() << 8 ^ (uint32_t)rand();
        size_t w = bhms_frame_encode(wire, sizeof wire, 2, 1, 0x7e7d7e7dULL, seq, payload, n);
        CHECK(w >= 24 + n);
        size_t stuffed = 0;
        for (size_t i = 1; i + 1 < w; ++i)
            if (wire[i] == 0x7d) ++stuffed;
        CHECK(w == 24 + n + stuffed); /* header holds 7e/7d bytes too: counted via escapes */
        hms_frame_parser p;
        hms_frame_reset(&p);
        hms_frame_result r = HMS_FRAME_NONE;
        for (size_t i = 0; i < w; ++i) {
            hms_frame_result x = hms_frame_feed(&p, wire[i]);
            if (x != HMS_FRAME_NONE) r = x;
        }
        CHECK(r == HMS_FRAME_READY);
        CHECK(p.raw[18] == (n >> 8) && p.raw[19] == (n & 0xff));
        CHECK(memcmp(p.raw + HMS_FRAME_HEADER, payload, n) == 0);
    }
    CHECK(bhms_frame_encode(wire, 10, 2, 1, 0, 0, payload, 5) == 0);          /* too small */
    CHECK(bhms_frame_encode(wire, sizeof wire, 2, 1, 0, 0, payload, 193) == 0); /* oversize */
}

/* The size-budget claim: an INVOKE with <= 8 argument bytes is <= 64 bytes. */
static void test_size_budget(void) {
    uint8_t b[32], wire[HMS_FRAME_WIRE_MAX];
    uint8_t args[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    size_t n = bhms_enc_invoke(b, 1, 0, 1, 100, args, 8);
    CHECK(n == 18);
    size_t w = bhms_frame_encode(wire, sizeof wire, 1, 1, 1, 0, b, n);
    CHECK(w == 42);
    CHECK(w <= 64);
}

int main(void) {
    test_spec_vectors();
    test_message_layouts();
    test_decoders();
    test_values();
    test_stuffing_roundtrip();
    test_size_budget();
    TEST_FINISH("test_codec");
}
