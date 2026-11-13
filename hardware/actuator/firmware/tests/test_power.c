/* E-stop / servo-rail supervisor: latch, restart inhibit, consistency rules, self-test,
 * overcurrent (INTERFACE.md sections 4 and 6). */
#include "arm_fault.h"
#include "bhms_test.h"
#include "power.h"

static power_in in_at(uint32_t t, int sense, uint32_t rail_mv, int32_t rail_ma) {
    power_in in = {t, (uint8_t)sense, 0, 1, rail_mv, rail_ma, 12000};
    return in;
}

/* Run the supervisor with a rail that follows the command (rise/fall in `lag` ms). */
typedef struct {
    power_sup p;
    uint32_t t, rail;
    int sense;
    int32_t ma;
} rig;

static void step(rig *r, uint32_t ms) {
    uint32_t k;
    for (k = 0; k < ms; ++k) {
        power_in in;
        ++r->t;
        r->rail = (r->p.rail_cmd && !r->sense) ? 12000u : 0u;
        in = in_at(r->t, r->sense, r->rail, r->rail ? r->ma : 0);
        power_update(&r->p, &in);
    }
}

static int enable(rig *r) {
    power_in in = in_at(r->t, r->sense, r->rail, 0);
    return power_request_enable(&r->p, &in);
}

static void test_conversions(void) {
    CHECK(ina219_bus_mv(0) == 0);
    CHECK(ina219_bus_mv((uint16_t)(3000u << 3)) == 12000); /* 4 mV LSB, bits 15..3 */
    CHECK(ina219_bus_mv((uint16_t)((3000u << 3) | 0x7u)) == 12000); /* status bits ignored */
    CHECK(ina219_current_ma(4000) == 1000); /* 0.25 mA LSB */
    CHECK(ina219_current_ma(-4) == -1);
    CHECK(power_vin_mv(4095) == 36300 && power_vin_mv(0) == 0 && power_vin_mv(60000) == 36300);
    CHECK(power_vin_mv(1015) > 9000 - 20 && power_vin_mv(1015) < 9000 + 20); /* 9 V threshold */
    /* CAL = trunc(0.04096 / (Current_LSB 0.00025 * R 0.01)) = 16384. */
    CHECK(INA219_CALIBRATION == 16384u && INA219_CONFIG == 0x299Fu);
}

static void test_selftest_and_enable(void) {
    rig r = {0};
    power_init(&r.p);
    step(&r, 5);
    CHECK(r.p.state == PWR_OFF && !r.p.rail_cmd && r.p.estop == ESTOP_RELEASED);
    CHECK(enable(&r) == PWR_ENABLE_OK);
    CHECK(r.p.state == PWR_ST_RISE && r.p.rail_cmd);
    step(&r, 49);
    CHECK(r.p.state == PWR_ST_RISE);
    step(&r, 1);
    CHECK(r.p.state == PWR_ST_FALL && !r.p.rail_cmd); /* rail was > 10 V after 50 ms: now cut */
    step(&r, 1);
    CHECK(r.p.selftest_done && r.p.state == PWR_RAMP && r.p.rail_cmd); /* fell below 2 V in time */
    step(&r, 1);
    CHECK(r.p.state == PWR_ON);
    /* The self-test runs once per boot. */
    r.p.state = PWR_OFF;
    r.p.rail_cmd = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK && r.p.state == PWR_RAMP);
}

static void test_selftest_failures(void) {
    rig r = {0};
    power_in in;
    power_init(&r.p);
    CHECK(enable(&r) == PWR_ENABLE_OK);
    /* The rail never rises: servo_rail path of the self-test fails after 50 ms. */
    for (r.t = 0; r.t < 60; ++r.t) {
        in = in_at(r.t, 0, 0, 0);
        power_update(&r.p, &in);
    }
    CHECK(r.p.state == PWR_FAULT && r.p.fault == ARM_FAULT_SELFTEST && !r.p.rail_cmd);
    /* The rail stays up after being switched off: Q2 stuck on, the fall check fails. */
    power_init(&r.p);
    r.t = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK);
    for (r.t = 1; r.t < 200; ++r.t) {
        in = in_at(r.t, 0, 12000, 100);
        power_update(&r.p, &in);
    }
    CHECK(r.p.state == PWR_FAULT && r.p.fault == ARM_FAULT_SELFTEST);
}

static void test_estop_latch_and_restart_inhibit(void) {
    rig r = {0};
    power_init(&r.p);
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    CHECK(r.p.state == PWR_ON);
    /* Press: the rail command drops in the same update; the latch is set. */
    r.sense = 1;
    {
        power_in in = in_at(r.t + 1, 1, 12000, 500);
        in.edge = 1;
        r.t++;
        power_update(&r.p, &in);
    }
    CHECK(!r.p.rail_cmd && r.p.latched && r.p.state == PWR_ESTOP && r.p.estop == ESTOP_PRESSED);
    CHECK(r.p.fault == ARM_FAULT_ESTOP);
    step(&r, 50);
    /* Release the mushroom: the rail must NOT come back by itself. */
    r.sense = 0;
    step(&r, 500);
    CHECK(!r.p.rail_cmd && r.p.latched && r.p.state == PWR_ESTOP && r.p.estop == ESTOP_RELEASED);
    /* Enable is refused while the contact is open, accepted once released. */
    r.sense = 1;
    CHECK(enable(&r) == PWR_REFUSE_ESTOP);
    r.sense = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK && !r.p.latched);
    step(&r, 20);
    CHECK(r.p.state == PWR_ON);
    /* A pulse shorter than the poll interval (edge only, level already low) still latches. */
    {
        power_in in = in_at(r.t + 1, 0, 12000, 100);
        in.edge = 1;
        r.t++;
        power_update(&r.p, &in);
    }
    CHECK(r.p.latched && !r.p.rail_cmd);
}

static void test_contact_fault(void) {
    /* GPIO8 high but the rail is still there after 20 ms: contact A welded or Q2 shorted. */
    rig r = {0};
    power_in in;
    power_init(&r.p);
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    for (r.t = r.t + 1; r.t < 1000; ++r.t) {
        in = in_at(r.t, 1, 12000, 300);
        if (r.t == 121 + 0) in.edge = 1;
        power_update(&r.p, &in);
        if (r.t < 121 + 20) CHECK(!r.p.hard_fault);
    }
    CHECK(r.p.hard_fault && r.p.estop == ESTOP_FAULT && r.p.fault == ARM_FAULT_ESTOP_CONTACT);
    /* Stay latched and refuse to enable, even with the contact reading released. */
    in = in_at(r.t, 0, 0, 0);
    CHECK(power_request_enable(&r.p, &in) == PWR_REFUSE_HARD_FAULT);
    CHECK(!r.p.rail_cmd);
    /* A normal press (rail decays within a few ms) is not a contact fault. */
    power_init(&r.p);
    r.t = 0;
    r.sense = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    r.sense = 1;
    step(&r, 100);
    CHECK(!r.p.hard_fault && r.p.state == PWR_ESTOP);
}

static void test_rail_fault_and_overcurrent(void) {
    rig r = {0};
    power_in in;
    power_init(&r.p);
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    CHECK(r.p.state == PWR_ON);
    /* Released contact, rail enabled, but the rail sags below 9 V: servo_rail_fault. */
    in = in_at(r.t + 1, 0, 8000, 100);
    power_update(&r.p, &in);
    CHECK(r.p.state == PWR_FAULT && r.p.fault == ARM_FAULT_SERVO_RAIL && !r.p.rail_cmd);
    /* A soft fault can be cleared and the enable retried. */
    power_clear_fault(&r.p);
    in = in_at(r.t + 2, 0, 0, 0);
    CHECK(power_request_enable(&r.p, &in) == PWR_ENABLE_OK);

    /* Overcurrent: > 4.5 A for 100 ms switches the rail off; 99 ms does not. */
    power_init(&r.p);
    r.t = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    r.ma = 4600;
    step(&r, 99);
    CHECK(r.p.state == PWR_ON);
    r.ma = 2000;
    step(&r, 5);
    r.ma = 4600;
    step(&r, 99);
    CHECK(r.p.state == PWR_ON); /* the dip reset the timer */
    step(&r, 3);
    CHECK(r.p.state == PWR_FAULT && r.p.fault == ARM_FAULT_OVERCURRENT && !r.p.rail_cmd);

    /* Warning at 3 A for 1 s: informational, the rail stays on. */
    power_init(&r.p);
    r.t = 0;
    r.ma = 3200;
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 1100);
    CHECK(r.p.state == PWR_ON && r.p.warn_overcurrent);
}

static void test_no_actuator_power_and_sense_failure(void) {
    rig r = {0};
    power_in in;
    power_init(&r.p);
    in = in_at(1, 0, 0, 0);
    in.vin_mv = 5000; /* USB only: not a fault, but no enable */
    CHECK(power_request_enable(&r.p, &in) == PWR_REFUSE_NO_POWER && r.p.fault == ARM_FAULT_NONE);
    in.vin_mv = 12000;
    in.ina_ok = 0;
    CHECK(power_request_enable(&r.p, &in) == PWR_REFUSE_SENSE);
    /* INA219 lost while the rail is on: after 20 failed reads the rail is cut. */
    power_init(&r.p);
    r.t = 0;
    CHECK(enable(&r) == PWR_ENABLE_OK);
    step(&r, 120);
    for (r.t = r.t + 1; r.t < 200; ++r.t) {
        in = in_at(r.t, 0, 0, 0);
        in.ina_ok = 0;
        power_update(&r.p, &in);
    }
    CHECK(r.p.state == PWR_FAULT && r.p.fault == ARM_FAULT_POWER_SENSE && !r.p.rail_cmd);
}

int main(void) {
    test_conversions();
    test_selftest_and_enable();
    test_selftest_failures();
    test_estop_latch_and_restart_inhibit();
    test_contact_fault();
    test_rail_fault_and_overcurrent();
    test_no_actuator_power_and_sense_failure();
    TEST_FINISH("test_power");
}
