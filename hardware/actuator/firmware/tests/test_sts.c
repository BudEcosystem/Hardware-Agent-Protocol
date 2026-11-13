/* STS3215 packet codec and bus-transaction tests (checksums, framing, echo, collisions). */
#include "bhms_test.h"
#include "sim_rig.h"
#include "sts.h"

static void test_encode_vectors(void) {
    uint8_t out[STS_FRAME_MAX];
    /* Hand-computed from CHK = ~(ID + LEN + INSTR + sum(P)) & 0xFF. */
    static const uint8_t ping1[] = {0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB};
    static const uint8_t read1[] = {0xFF, 0xFF, 0x01, 0x04, 0x02, 0x38, 0x02, 0xBE};
    static const uint8_t torque[] = {0xFF, 0xFF, 0x01, 0x04, 0x03, 0x28, 0x01, 0xCE};
    static const uint8_t sync[] = {0xFF, 0xFF, 0xFE, 0x0A, 0x83, 0x2A, 0x02, 0x01, 0x00, 0x08,
                                   0x02, 0x00, 0x08, 0x35};
    uint8_t p[2] = {0x38, 0x02}, w[2] = {0x28, 0x01}, ids[2] = {1, 2}, data[4] = {0x00, 0x08, 0x00, 0x08};
    CHECK(sts_encode(out, sizeof out, 1, STS_INSTR_PING, 0, 0) == sizeof ping1);
    CHECK_BYTES(out, ping1, sizeof ping1);
    CHECK(sts_encode(out, sizeof out, 1, STS_INSTR_READ, p, 2) == sizeof read1);
    CHECK_BYTES(out, read1, sizeof read1);
    CHECK(sts_encode(out, sizeof out, 1, STS_INSTR_WRITE, w, 2) == sizeof torque);
    CHECK_BYTES(out, torque, sizeof torque);
    CHECK(sts_encode_sync_write(out, sizeof out, 0x2A, 2, 2, ids, data) == sizeof sync);
    CHECK_BYTES(out, sync, sizeof sync);
    /* Bounds: too many parameters, too small a buffer. */
    CHECK(sts_encode(out, sizeof out, 1, STS_INSTR_WRITE, out, STS_MAX_PARAMS + 1u) == 0);
    CHECK(sts_encode(out, 5, 1, STS_INSTR_PING, 0, 0) == 0);
    CHECK(sts_encode_sync_write(out, sizeof out, 0x2A, 7, 8, ids, data) == 0);
}

static void test_decode(void) {
    sts_status st;
    uint8_t good[] = {0xFF, 0xFF, 0x03, 0x04, 0x00, 0x12, 0x34, 0x00};
    good[7] = sts_checksum(&good[2], 5);
    CHECK(sts_decode(good, sizeof good, &st) == STS_OK);
    CHECK(st.id == 3 && st.error == 0 && st.n == 2 && st.params[0] == 0x12 && st.params[1] == 0x34);
    good[5] ^= 1;
    CHECK(sts_decode(good, sizeof good, &st) == STS_E_CHECKSUM);
    good[5] ^= 1;
    CHECK(sts_decode(good, 7, &st) == STS_E_SHORT);
    good[0] = 0;
    CHECK(sts_decode(good, sizeof good, &st) == STS_E_HEADER);
    good[0] = 0xFF;
    good[3] = 1; /* LEN < 2 */
    CHECK(sts_decode(good, sizeof good, &st) == STS_E_LENGTH);
    good[3] = 250; /* parameters would not fit */
    CHECK(sts_decode(good, sizeof good, &st) == STS_E_LENGTH);
    /* Sign-magnitude helpers. */
    CHECK(sts_sm_decode(0x8005, 15) == -5 && sts_sm_decode(5, 15) == 5);
    CHECK(sts_sm_encode(-5, 15) == 0x8005 && sts_sm_encode(5, 15) == 5);
    CHECK(sts_sm_decode(sts_sm_encode(-27306, 15), 15) == -27306);
    CHECK(sts_sm_decode(0x0400 | 300, 10) == -300);
}

static void test_bus(void) {
    sim_rig r;
    sts_bus bus;
    uint8_t buf[4];
    sts_status st;
    uint8_t err = 9, v = 1;
    sim_rig_init(&r);
    sts_bus_init(&bus, &r.hw);
    /* Unpowered servos do not answer. */
    CHECK(sts_bus_ping(&bus, 1, &st) == STSB_TIMEOUT && bus.timeouts == 1);
    r.servo_en_pin = 1;
    sim_rig_advance(&r, 20);
    CHECK(sts_bus_ping(&bus, 1, &st) == STSB_OK && st.id == 1);
    CHECK(sts_bus_ping(&bus, 7, &st) == STSB_TIMEOUT); /* no such servo */
    /* READ: present position of servo 1 is 2048 = 0x0800. */
    CHECK(sts_bus_read(&bus, 1, STS_REG_PRESENT_POSITION, 2, buf, &err) == STSB_OK);
    CHECK(sts_get16(buf) == 2048 && err == 0);
    /* The EEPROM is locked at power-up: a write is ACKed but ignored; unlocking enables it. */
    CHECK(sts_bus_write(&bus, 1, STS_REG_RETURN_DELAY, &v, 1) == STSB_OK);
    CHECK(sim_rig_reg8(&r, 1, STS_REG_RETURN_DELAY) == 250);
    v = 0;
    CHECK(sts_bus_write(&bus, 1, STS_REG_LOCK, &v, 1) == STSB_OK);
    v = 1;
    CHECK(sts_bus_write(&bus, 1, STS_REG_RETURN_DELAY, &v, 1) == STSB_OK);
    CHECK(sim_rig_reg8(&r, 1, STS_REG_RETURN_DELAY) == 1);
    /* Broadcast sync write reaches every listed servo, no reply expected. */
    {
        uint8_t ids[2] = {1, 2}, on[2] = {1, 1};
        CHECK(sts_bus_sync_write(&bus, STS_REG_TORQUE_ENABLE, 1, 2, ids, on) == STSB_OK);
        CHECK(sim_rig_reg8(&r, 1, STS_REG_TORQUE_ENABLE) == 1 && sim_rig_reg8(&r, 2, STS_REG_TORQUE_ENABLE) == 1);
    }
    /* A corrupted echo is a bus collision, and counted. */
    r.corrupt_echo_once = 1;
    CHECK(sts_bus_ping(&bus, 1, &st) == STSB_COLLISION && bus.collisions == 1);
    CHECK(sts_bus_ping(&bus, 1, &st) == STSB_OK); /* recovers */
    /* A reply from the wrong servo is rejected (no silent acceptance). */
    CHECK(sts_bus_read(&bus, 1, 0, 0, buf, 0) == STSB_ARG);
    CHECK(sts_bus_read(&bus, 1, STS_REG_PRESENT_POSITION, STS_MAX_PARAMS + 1u, buf, 0) == STSB_ARG);
}

int main(void) {
    test_encode_vectors();
    test_decode();
    test_bus();
    TEST_FINISH("test_sts");
}
