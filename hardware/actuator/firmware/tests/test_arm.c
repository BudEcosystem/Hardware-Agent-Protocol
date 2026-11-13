/* Arm controller core against the simulated rig: enable sequence, limit enforcement, torque
 * caps, E-stop behaviour, tool change, stop. Every check runs under ASan/UBSan. */
#include <math.h>
#include <stdlib.h>

#include "arm.h"
#include "bhms_test.h"
#include "sim_rig.h"

typedef struct tb {
    sim_rig rig;
    arm a;
    arm_sink sink;
    arm_completion done;
    unsigned n_done, n_progress, n_stop_confirmed;
    uint8_t stop_measured;
    float max_cmd_dps[ARM_NUM_JOINTS];   /* fastest commanded waypoint seen, deg/s */
    arm_pose prev_q;
    int track_speed;
    int track_pose_violation;            /* a real servo position outside the limits (2 deg slack) */
    unsigned pose_violations;
    unsigned max_goal_raw_elbow;
    void (*hook)(struct tb *);
} tb;

static void s_finished(void *c, const arm_completion *d) { tb *t = (tb *)c; t->done = *d; ++t->n_done; }
static void s_progress(void *c, uint8_t p) { (void)p; ++((tb *)c)->n_progress; }
static void s_stop(void *c, uint8_t m) { tb *t = (tb *)c; t->stop_measured = m; ++t->n_stop_confirmed; }

static int g_wdt;           /* next tb_init: the previous reset was the watchdog */
static uint32_t g_start_ms; /* next tb_init: start the millisecond clock here */

static void tb_init(tb *t) {
    memset(t, 0, sizeof *t);
    sim_rig_init(&t->rig);
    t->rig.watchdog_reset = g_wdt;
    t->rig.now_ms = g_start_ms;
    t->sink.ctx = t;
    t->sink.finished = s_finished;
    t->sink.progress = s_progress;
    t->sink.stop_confirmed = s_stop;
    {
        arm_cal cal;
        arm_cal_nominal(&cal);
        arm_init(&t->a, &t->rig.hw, &cal, &t->sink);
    }
}

static float joint_deg(tb *t, unsigned j) {
    return arm_from_raw(&t->a.cal, j, (int32_t)lround(sim_rig_pos(&t->rig, kArmServos[j].servo_id)));
}

static void run(tb *t, uint32_t ms) {
    uint32_t k;
    for (k = 0; k < ms; ++k) {
        sim_rig_advance(&t->rig, 1);
        arm_tick(&t->a);
        if (t->hook) t->hook(t);
        if (t->track_speed && t->a.traj_active) {
            unsigned j;
            for (j = 0; j < ARM_NUM_JOINTS; ++j) {
                /* waypoints are written every 20 ms: speed = delta / 0.02 s */
                float d = fabsf(t->a.q_cmd.q[j] - t->prev_q.q[j]) * 50.0f;
                if (d > t->max_cmd_dps[j]) t->max_cmd_dps[j] = d;
            }
        }
        t->prev_q = t->a.q_cmd;
        if (t->track_pose_violation) {
            arm_pose p;
            unsigned j;
            for (j = 0; j < ARM_NUM_JOINTS; ++j) p.q[j] = joint_deg(t, j);
            if (arm_check_pose(&p, -2.0f) != ARM_LIMIT_NONE) ++t->pose_violations;
        }
        {
            unsigned g = sim_rig_reg16(&t->rig, 3, STS_REG_GOAL_POSITION);
            if (t->rig.sv[3].ram[STS_REG_TORQUE_ENABLE] && g > t->max_goal_raw_elbow) t->max_goal_raw_elbow = g;
        }
    }
}

static int run_until_idle(tb *t, uint32_t max_ms) {
    uint32_t k;
    for (k = 0; k < max_ms; ++k) {
        run(t, 1);
        if (t->a.op == ARM_OP_NONE) return 1;
    }
    return 0;
}

static void bring_up(tb *t) {
    uint8_t d;
    tb_init(t);
    run(t, 100);
    CHECK(arm_cmd_enable(&t->a, &d) == ARM_OK);
    CHECK(run_until_idle(t, 4000));
    CHECK(t->a.state == ARM_ST_READY);
    t->n_done = 0;
}

static arm_refusal move(tb *t, float a, float b, float c, float d, float e, uint8_t pct, uint8_t *det) {
    float q[5] = {a, b, c, d, e};
    return arm_cmd_move(&t->a, q, pct, det);
}

/* ---- Tests ---------------------------------------------------------------------------- */
static void test_boot_states(void) {
    tb t;
    tb_init(&t);
    t.rig.vin_mv = 5000; /* USB only */
    run(&t, 100);
    CHECK(t.a.state == ARM_ST_NO_POWER && !t.rig.servo_en_pin && !t.rig.tool_en_pin);
    CHECK(t.a.fault_code == ARM_FAULT_NONE); /* reported as "no actuator power", not as a fault */
    {
        uint8_t d;
        CHECK(arm_cmd_enable(&t.a, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NO_POWER);
        CHECK(!t.rig.servo_en_pin); /* the rail is never switched on */
    }
    t.rig.vin_mv = 12000;
    run(&t, 200);
    CHECK(t.a.state == ARM_ST_DISABLED);
    /* Reset defaults were asserted at init: rail and tool power off. */
    CHECK(!t.rig.servo_en_pin && !t.rig.tool_en_pin && t.rig.rail_mv < 100);
}

static void test_enable_sequence(void) {
    tb t;
    unsigned j;
    uint8_t d;
    tb_init(&t);
    run(&t, 100);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && t.a.state == ARM_ST_ENABLING);
    {
        float q[5] = {0, 30, 90, 45, 0};
        CHECK(arm_cmd_move(&t.a, q, 50, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NOT_ENABLED); /* not yet */
    }
    CHECK(run_until_idle(&t, 4000));
    CHECK(t.done.kind == ARM_OP_ENABLE && t.done.status == ARM_DONE_COMPLETED && t.done.measured);
    CHECK(t.a.state == ARM_ST_READY && t.a.torque_on && !t.a.pose_unknown && t.a.pwr.selftest_done);
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        unsigned id = kArmServos[j].servo_id;
        int32_t lo, hi;
        CHECK(arm_to_raw(&t.a.cal, j, kArmServos[j].lo_deg, &lo) == 0);
        CHECK(arm_to_raw(&t.a.cal, j, kArmServos[j].hi_deg, &hi) == 0);
        CHECK(sim_rig_reg8(&t.rig, id, STS_REG_TORQUE_ENABLE) == 1);
        CHECK(sim_rig_reg8(&t.rig, id, STS_REG_RETURN_DELAY) == 0);
        CHECK(sim_rig_reg16(&t.rig, id, STS_REG_MIN_ANGLE) == (unsigned)lo);
        CHECK(sim_rig_reg16(&t.rig, id, STS_REG_MAX_ANGLE) == (unsigned)hi);
        CHECK(sim_rig_reg16(&t.rig, id, STS_REG_MAX_TORQUE) == kArmServos[j].torque_permille);
        CHECK(sim_rig_reg16(&t.rig, id, STS_REG_TORQUE_LIMIT) == kArmServos[j].torque_permille);
        CHECK(sim_rig_reg8(&t.rig, id, 0x37) == 1); /* EEPROM locked again */
        /* Goal = present position: nothing moved when torque came on. */
        CHECK(fabs((double)sim_rig_reg16(&t.rig, id, STS_REG_GOAL_POSITION) - sim_rig_pos(&t.rig, id)) < 1.5);
    }
    /* The shoulder cap is the design requirement: 78 % = 780 of 1000, EEPROM and RAM. */
    CHECK(sim_rig_reg16(&t.rig, 2, STS_REG_MAX_TORQUE) == 780 && sim_rig_reg16(&t.rig, 2, STS_REG_TORQUE_LIMIT) == 780);
    CHECK(sim_rig_reg16(&t.rig, 1, STS_REG_MAX_TORQUE) == 1000);
    CHECK(t.rig.servo_en_pin && t.rig.rail_mv > 11000 && t.rig.led[1] == 1); /* green */
    /* Enabling an enabled arm is a no-op. */
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && t.a.op == ARM_OP_NONE);
}

static void test_enable_failures(void) {
    tb t;
    uint8_t d;
    /* A servo whose EEPROM does not take the writes: the read-back fails, the enable ends
     * with a config fault and the rail is cut again; nothing is left energised. */
    tb_init(&t);
    t.rig.sv[2].ignore_eeprom_writes = 1;
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_CONFIG);
    CHECK(t.a.state == ARM_ST_DISABLED && !t.rig.servo_en_pin && !t.a.torque_on);
    CHECK(sim_rig_reg8(&t.rig, 1, STS_REG_TORQUE_ENABLE) == 0);

    /* A servo that does not answer. */
    tb_init(&t);
    t.rig.sv[4].present = 0;
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_SERVO_COMM && !t.rig.servo_en_pin);

    /* The arm was left in a pose that violates a coupled limit (moved by hand): torque is
     * never enabled. shoulder 80 + elbow 100 = 180 > 175. */
    tb_init(&t);
    {
        int32_t rs, re;
        CHECK(arm_to_raw(&t.a.cal, ARM_J_SHOULDER, 80, &rs) == 0 && arm_to_raw(&t.a.cal, ARM_J_ELBOW, 100, &re) == 0);
        sim_rig_place(&t.rig, 2, rs);
        sim_rig_place(&t.rig, 3, re);
    }
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_LIMIT);
    CHECK(t.a.move_limit == ARM_LIMIT_COUPLED_BASE + 0);
    CHECK(sim_rig_reg8(&t.rig, 2, STS_REG_TORQUE_ENABLE) == 0 && !t.a.torque_on);
    /* A pose within 3 degrees of the limit is refused too (margin on the measured pose). */
    tb_init(&t);
    {
        int32_t rs, re;
        CHECK(arm_to_raw(&t.a.cal, ARM_J_SHOULDER, 80, &rs) == 0 && arm_to_raw(&t.a.cal, ARM_J_ELBOW, 93.5f, &re) == 0);
        sim_rig_place(&t.rig, 2, rs);
        sim_rig_place(&t.rig, 3, re);
    }
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_LIMIT);
}

static void test_move_in_limits(void) {
    tb t;
    uint8_t d = 0;
    unsigned j;
    bring_up(&t);
    t.track_speed = 1;
    t.track_pose_violation = 1;
    CHECK(move(&t, 40, 45, 70, 20, -30, 50, &d) == ARM_OK);
    CHECK(t.a.state == ARM_ST_MOVING && t.a.op == ARM_OP_MOVE);
    CHECK(run_until_idle(&t, 12000));
    CHECK(t.done.kind == ARM_OP_MOVE && t.done.status == ARM_DONE_COMPLETED && t.done.measured);
    CHECK(t.done.values[0] < 2.0f);
    CHECK(t.a.state == ARM_ST_READY && t.n_progress > 0);
    {
        const float want[5] = {40, 45, 70, 20, -30};
        for (j = 0; j < 5; ++j) CHECK(fabsf(joint_deg(&t, j) - want[j]) < 2.0f);
    }
    /* The commanded waypoints never exceed 50 % of the per-joint speed limit (shoulder 1/3,
     * elbow 1/2 of the servo speed) and the real servos never left the allowed region. */
    for (j = 0; j < 5; ++j) CHECK(t.max_cmd_dps[j] <= arm_speed_limit_dps(j) * 0.5f * 1.04f);
    CHECK(t.max_cmd_dps[ARM_J_SHOULDER] > 0.0f);
    CHECK(t.pose_violations == 0);
    /* Measured properties follow the motion. */
    CHECK(fabsf(t.a.sv[ARM_J_BASE_YAW].pos_deg - 40.0f) < 2.5f && t.a.sv[ARM_J_BASE_YAW].valid);
    /* The servo-side speed cap was also written (second layer): never above 50 % * 1.25 + margin. */
    CHECK(sim_rig_reg16(&t.rig, 1, STS_REG_GOAL_SPEED) < 3064u * 70u / 100u);
}

static void test_limit_refusals(void) {
    tb t;
    uint8_t d = 0;
    unsigned j;
    uint32_t frames;
    bring_up(&t);
    frames = t.rig.frames;
    {
        /* Every joint at its extreme +1 degree: refused naming the joint. */
        static const float base[5] = {0, 30, 90, 45, 0};
        float hi[5] = {150, 95, 125, 100, 150}, lo[5] = {-150, -20, -5, -100, -150};
        for (j = 0; j < 5; ++j) {
            float q[5];
            memcpy(q, base, sizeof q);
            q[j] = hi[j] + 1.0f;
            CHECK(arm_cmd_move(&t.a, q, 50, &d) == ARM_REFUSE_RANGE && d == j);
            q[j] = lo[j] - 1.0f;
            CHECK(arm_cmd_move(&t.a, q, 50, &d) == ARM_REFUSE_RANGE && d == j);
        }
    }
    /* Coupled limits, each named. */
    CHECK(move(&t, 0, 80, 100, 0, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0x10);  /* 180 > 175 */
    CHECK(move(&t, 0, 0, 100, 70, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0x11);  /* 170 > 165 */
    CHECK(move(&t, 0, 50, 40, 95, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0x12);  /* 185 > 183 */
    CHECK(move(&t, 0, 30, 100, 100, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0x11); /* INTERFACE.md example */
    CHECK(move(&t, NAN, 0, 0, 0, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0);
    CHECK(move(&t, 0, 30, 90, 45, 0, 4, &d) == ARM_REFUSE_RANGE && d == 0xF0);   /* speed */
    CHECK(move(&t, 0, 30, 90, 45, 0, 101, &d) == ARM_REFUSE_RANGE);
    /* A refused goal does not touch the bus or the arm. */
    CHECK(t.rig.frames == frames && t.a.op == ARM_OP_NONE && t.a.state == ARM_ST_READY);
    /* A goal exactly on a coupled limit is accepted. */
    CHECK(move(&t, 0, 80, 95, 0, 0, 100, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 12000) && t.done.status == ARM_DONE_COMPLETED);
    /* Not enabled: the range error still wins (it does not depend on state). */
    tb_init(&t);
    run(&t, 50);
    CHECK(move(&t, 0, 80, 100, 0, 0, 50, &d) == ARM_REFUSE_RANGE && d == 0x10);
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NOT_ENABLED);
}

static void test_waypoint_layer_is_independent(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 40, 60, 20, 0, 50, &d) == ARM_OK);
    run(&t, 100);
    /* Corrupt the trajectory goal behind the command check (a memory fault, a bug): the
     * waypoint check must still stop the arm before a violating goal is written. */
    t.a.q_goal.q[ARM_J_ELBOW] = 140.0f;
    t.a.traj_ms = 4000; /* slow enough for the servos to follow: only the waypoint check can object */
    CHECK(run_until_idle(&t, 12000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_LIMIT);
    CHECK(t.a.move_limit == ARM_J_ELBOW);
    {
        int32_t hi;
        CHECK(arm_to_raw(&t.a.cal, ARM_J_ELBOW, 125.0f, &hi) == 0);
        CHECK(t.max_goal_raw_elbow <= (unsigned)hi); /* no goal beyond the elbow limit ever reached the servo */
    }
    CHECK(t.a.state == ARM_ST_READY && t.a.torque_on); /* still holding */
}

static void test_estop_in_motion(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 60, 50, 80, 30, 40, 40, &d) == ARM_OK);
    run(&t, 300);
    CHECK(t.a.state == ARM_ST_MOVING);
    /* Press: the GPIO IRQ clears SERVO_EN at once (hardware cut the rail already). */
    sim_rig_press_estop(&t.rig, 1);
    CHECK(t.rig.servo_en_pin == 0 && t.rig.estop_cuts == 1);
    /* One firmware tick later: latched, command cleared, operation failed with the E-stop fault. */
    run(&t, 1);
    CHECK(t.a.pwr.latched && !t.a.pwr.rail_cmd && t.a.state == ARM_ST_ESTOP);
    CHECK(t.n_done == 1 && t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_ESTOP);
    CHECK(arm_estop_state(&t.a) == ESTOP_PRESSED && t.a.fault_code == ARM_FAULT_ESTOP);
    CHECK(t.a.pose_unknown && !t.a.torque_on); /* "arm may have moved: re-home before use" */
    run(&t, 20);
    CHECK(t.rig.rail_mv < 100 && t.rig.falls >= 1 && t.a.rail_mv < 2000); /* measured dead */
    /* While pressed: nothing moves, enable is refused. */
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_INHIBITED);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_ESTOP_PRESSED);
    /* Release the mushroom: the rail must not come back, motion stays refused (restart inhibit). */
    sim_rig_press_estop(&t.rig, 0);
    run(&t, 800);
    CHECK(!t.rig.servo_en_pin && t.rig.rail_mv < 100 && t.a.state == ARM_ST_ESTOP);
    CHECK(arm_estop_state(&t.a) == ESTOP_RELEASED && t.a.pwr.latched);
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_ESTOP_LATCHED);
    {
        uint8_t m;
        CHECK(arm_stop(&t.a, &m) == ARM_STOP_CONFIRMED && m == 1); /* nothing can move: rail measured dead */
    }
    /* Explicit enable with the contact released brings it back, without a second self-test. */
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.a.state == ARM_ST_READY && !t.a.pose_unknown && t.a.torque_on);
    CHECK(!t.a.pwr.latched && t.a.fault_code == ARM_FAULT_NONE);
}

static void test_estop_contact_fault(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    t.rig.contact_a_welded = 1; /* Q2 stays on although the button is pressed */
    sim_rig_press_estop(&t.rig, 1);
    run(&t, 100);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.pwr.hard_fault && arm_estop_state(&t.a) == ESTOP_FAULT);
    CHECK(t.a.fault_code == ARM_FAULT_ESTOP_CONTACT && !t.a.pwr.rail_cmd);
    sim_rig_press_estop(&t.rig, 0);
    t.rig.contact_a_welded = 0;
    run(&t, 200);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_HARD_FAULT);
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_HARD_FAULT);
}

static void test_rail_faults(void) {
    tb t;
    bring_up(&t);
    t.rig.vin_mv = 7000; /* supply sags: the rail collapses with the contact released */
    run(&t, 100);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_SERVO_RAIL && !t.a.pwr.rail_cmd);
    bring_up(&t);
    t.rig.extra_ma = 5000; /* a short or a stalled arm */
    run(&t, 150);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_OVERCURRENT && !t.rig.servo_en_pin);
}

static void test_home_and_release(void) {
    tb t;
    uint8_t d = 0;
    unsigned j;
    bring_up(&t);
    CHECK(move(&t, 30, 60, 50, 10, 20, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    CHECK(arm_cmd_release(&t.a, &d) == ARM_OK);
    t.track_speed = 1;
    CHECK(run_until_idle(&t, 30000));
    CHECK(t.done.kind == ARM_OP_RELEASE && t.done.status == ARM_DONE_COMPLETED);
    CHECK(t.a.state == ARM_ST_PARKED && !t.a.torque_on);
    for (j = 0; j < 5; ++j) {
        CHECK(fabsf(joint_deg(&t, j) - kArmRestPose[j]) < 2.0f); /* parked on the rest pose first */
        CHECK(sim_rig_reg8(&t.rig, kArmServos[j].servo_id, STS_REG_TORQUE_ENABLE) == 0);
        CHECK(t.max_cmd_dps[j] <= arm_speed_limit_dps(j) * 0.25f * 1.04f); /* reduced speed */
    }
    CHECK(t.rig.servo_en_pin && t.rig.falls == 0); /* torque off, rail still on, nothing fell */
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_PARKED);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.a.state == ARM_ST_READY && t.rig.falls == 0);
    /* Home from a far pose: capped at 30 % speed. */
    CHECK(move(&t, -60, 10, 20, -20, 60, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    memset(t.max_cmd_dps, 0, sizeof t.max_cmd_dps);
    CHECK(arm_cmd_home(&t.a, 100, &d) == ARM_OK && run_until_idle(&t, 30000));
    for (j = 0; j < 5; ++j) {
        CHECK(fabsf(joint_deg(&t, j) - kArmRestPose[j]) < 2.0f);
        CHECK(t.max_cmd_dps[j] <= arm_speed_limit_dps(j) * 0.30f * 1.04f);
    }
}

static void test_hold_cancel_and_stop(void) {
    tb t;
    uint8_t d = 0, m = 0;
    double before, after;
    bring_up(&t);
    CHECK(move(&t, 100, 60, 50, 10, 20, 30, &d) == ARM_OK);
    run(&t, 400);
    CHECK(arm_cmd_hold(&t.a, &d) == ARM_OK);
    CHECK(t.n_done == 1 && t.done.status == ARM_DONE_CANCELED && t.a.state == ARM_ST_READY);
    run(&t, 300);
    before = sim_rig_pos(&t.rig, 1);
    run(&t, 300);
    after = sim_rig_pos(&t.rig, 1);
    CHECK(fabs(after - before) < 1.5 && joint_deg(&t, 0) < 99.0f); /* frozen short of the goal */
    /* STOP during a motion: initiated, then confirmed from the servos' Moving flags. */
    CHECK(move(&t, -100, 40, 70, 0, -20, 50, &d) == ARM_OK);
    run(&t, 300);
    t.n_stop_confirmed = 0;
    CHECK(arm_stop(&t.a, &m) == ARM_STOP_INITIATED && t.a.op == ARM_OP_NONE);
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_STOPPING);
    run(&t, 600);
    CHECK(t.n_stop_confirmed == 1 && t.stop_measured == 1);
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_OK); /* usable again after the stop */
    run_until_idle(&t, 12000);
}

static void test_servo_lost_and_bus_collision(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    t.rig.drop_reply_mask = 1u << 3;
    run(&t, 400);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_SERVO_COMM);
    CHECK(t.rig.servo_en_pin); /* the other servos keep holding */
    bring_up(&t);
    CHECK(move(&t, 80, 40, 60, 0, 0, 40, &d) == ARM_OK);
    t.rig.corrupt_echo_always = 1; /* every frame's echo is damaged: a real bus fault */
    run_until_idle(&t, 500);
    t.rig.corrupt_echo_always = 0;
    if (t.done.fault != ARM_FAULT_BUS) fprintf(stderr, "bus test: status %u fault %u coll %u op %d state %d\n", t.done.status, t.done.fault, t.a.bus.collisions, t.a.op, t.a.state);
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_BUS && t.a.bus.collisions >= 3);
}

static uint8_t g_fsr_contact_enabled;
static void fsr_hook(tb *t) {
    if (!g_fsr_contact_enabled) return;
    {
        double p = sim_rig_pos(&t->rig, 8);
        double over = p - 1883.0; /* contact at 3 mm depth */
        t->rig.aux1_code = (uint16_t)(100.0 + (over > 0.0 ? over * 8.0 : 0.0));
    }
}

static void test_tools(void) {
    tb t;
    uint8_t d = 0;
    int32_t raw;
    bring_up(&t);
    /* No tool: mount refused. */
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NO_TOOL);
    /* A reserved ID (2 k): detected but not mountable. */
    sim_rig_set_tool(&t.rig, 2000.0);
    run(&t, 100);
    CHECK(t.a.tool_id == 5 && arm_cmd_tool_mount(&t.a, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_TOOL_RESERVED);
    /* Gripper: detect (5 stable samples), unpowered until mounted. */
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 20);
    CHECK(t.a.tool_state != TOOL_ST_READY && !t.rig.tool_en_pin);
    run(&t, 100);
    CHECK(t.a.tool_id == ARM_TOOL_GRIPPER && t.a.tool_state == TOOL_ST_DETECTED && !t.rig.tool_en_pin);
    CHECK(arm_cmd_grip(&t.a, 30, 10, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_TOOL_NOT_READY);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && t.rig.tool_en_pin && t.a.tool_state == TOOL_ST_POWERING);
    CHECK(run_until_idle(&t, 3000));
    CHECK(t.done.kind == ARM_OP_TOOL_MOUNT && t.done.status == ARM_DONE_COMPLETED && t.a.tool_state == TOOL_ST_READY);
    CHECK(sim_rig_reg16(&t.rig, 6, STS_REG_MAX_TORQUE) == 150); /* gripper: at most 15 % */
    CHECK(sim_rig_reg8(&t.rig, 6, STS_REG_TORQUE_ENABLE) == 1);
    /* Argument limits. */
    CHECK(arm_cmd_grip(&t.a, 61, 10, &d) == ARM_REFUSE_RANGE && d == 0);
    CHECK(arm_cmd_grip(&t.a, 30, 16, &d) == ARM_REFUSE_RANGE && d == 1);
    CHECK(arm_cmd_grip(&t.a, 30, 0, &d) == ARM_REFUSE_RANGE);
    CHECK(arm_cmd_turn(&t.a, 10, 5, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_WRONG_TOOL);
    /* Open to 40 mm with 10 % force. */
    CHECK(arm_cmd_grip(&t.a, 40, 10, &d) == ARM_OK && run_until_idle(&t, 8000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && fabsf(t.done.values[0] - 40.0f) < 1.5f && t.done.values[1] < 0.5f);
    CHECK(sim_rig_reg16(&t.rig, 6, STS_REG_TORQUE_LIMIT) == 100); /* force limit on the servo */
    /* Close on a 20 mm object: the fingers stall short of the target -> grasped. */
    CHECK(arm_to_raw(&t.a.cal, ARM_S_GRIPPER, 10.0f / 12.0f * (180.0f / 3.14159265f), &raw) == 0);
    t.rig.sv[6].block_lo = raw;
    CHECK(arm_cmd_grip(&t.a, 0, 15, &d) == ARM_OK && run_until_idle(&t, 8000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.done.values[1] > 0.5f && fabsf(t.done.values[0] - 20.0f) < 1.5f);
    CHECK(sim_rig_reg16(&t.rig, 6, STS_REG_TORQUE_LIMIT) == 150);
    {
        uint8_t valid;
        CHECK(fabsf(arm_gripper_opening_mm(&t.a, &valid) - 20.0f) < 1.5f && valid);
    }
    /* Unmount: torque off, TOOL_EN cleared, 60 ms discharge before it reports done. */
    t.rig.sv[6].block_lo = -1e9;
    CHECK(arm_cmd_tool_unmount(&t.a, &d) == ARM_OK);
    run(&t, 10);
    CHECK(!t.rig.tool_en_pin && t.a.op == ARM_OP_TOOL_UNMOUNT && t.a.tool_state == TOOL_ST_UNMOUNTING);
    CHECK(run_until_idle(&t, 500) && t.a.tool_state == TOOL_ST_DETECTED);
    CHECK(sim_rig_reg8(&t.rig, 6, STS_REG_TORQUE_ENABLE) == 0);
}

static void test_tool_hot_unplug_and_estop(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(arm_cmd_grip(&t.a, 50, 10, &d) == ARM_OK);
    run(&t, 50);
    sim_rig_set_tool(&t.rig, -1.0); /* knocked off */
    run(&t, 15);
    CHECK(!t.rig.tool_en_pin && t.a.tool_state == TOOL_ST_LOST && t.a.fault_code == ARM_FAULT_TOOL_LOST);
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_TOOL_LOST);
    /* A tool change is refused while the E-stop is not released. */
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 150);
    sim_rig_press_estop(&t.rig, 1);
    run(&t, 20);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_REFUSE_INHIBITED);
    CHECK(arm_cmd_tool_unmount(&t.a, &d) == ARM_REFUSE_INHIBITED);
    CHECK(!t.rig.tool_en_pin);
    sim_rig_press_estop(&t.rig, 0);
    run(&t, 50);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_ESTOP_LATCHED);
}

static void test_knob_and_presser(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 3300.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000) && t.a.tool_state == TOOL_ST_READY);
    /* Multi-turn ABSOLUTE position mode (mode 0, both angle limits 0), never the relative step mode. */
    CHECK(sim_rig_reg8(&t.rig, 7, STS_REG_OPERATING_MODE) == STS_MODE_POSITION);
    CHECK(sim_rig_reg16(&t.rig, 7, STS_REG_MIN_ANGLE) == 0 && sim_rig_reg16(&t.rig, 7, STS_REG_MAX_ANGLE) == 0);
    CHECK(fabs(sim_rig_pos(&t.rig, 7)) < 1.0); /* mounting commanded no motion (goal = present) */
    CHECK(sim_rig_reg16(&t.rig, 7, STS_REG_MAX_TORQUE) == 25); /* 2.5 %: keeps the flexure within +-25 deg */
    CHECK(arm_cmd_turn(&t.a, 1300, 10, &d) == ARM_REFUSE_RANGE && d == 0);
    CHECK(arm_cmd_turn(&t.a, 90, 26, &d) == ARM_REFUSE_RANGE && d == 1);
    CHECK(arm_cmd_turn(&t.a, 360, 20, &d) == ARM_OK && run_until_idle(&t, 30000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.done.values[1] > 0.5f && fabsf(t.done.values[0] - 360.0f) < 3.0f);
    CHECK(fabs(sim_rig_pos(&t.rig, 7) - 8192.0) < 20.0); /* 20:40 spur: 2 servo turns per knob turn */
    CHECK(sim_rig_reg16(&t.rig, 7, STS_REG_TORQUE_LIMIT) == 20);
    /* A mechanical stop at 180 knob degrees: reached = false, position measured. */
    t.rig.sv[7].block_hi = 4096.0;
    CHECK(arm_cmd_turn(&t.a, 720, 20, &d) == ARM_OK && run_until_idle(&t, 30000));
    /* Stopped short: a FAILURE (stall), not a completion; the partial effect is readable. */
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_STALL);
    CHECK(fabsf(t.a.sv[ARM_S_KNOB].pos_deg - 180.0f) < 3.0f && fabsf(t.done.values[0] - 180.0f) < 3.0f);
    t.rig.sv[7].block_hi = 1e9;
    CHECK(arm_cmd_turn(&t.a, -90, 25, &d) == ARM_OK && run_until_idle(&t, 30000));
    CHECK(fabsf(t.done.values[0] + 90.0f) < 3.0f);

    /* Button presser with a force limit. */
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 10000.0);
    t.hook = fsr_hook;
    g_fsr_contact_enabled = 1;
    t.rig.sv[8].block_hi = 1883.0 + 400.0;
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(t.a.fsr_base == 100 && sim_rig_reg16(&t.rig, 8, STS_REG_MAX_TORQUE) == 200);
    CHECK(arm_cmd_press(&t.a, 8.0f, 20, &d) == ARM_REFUSE_RANGE && d == 0);
    CHECK(arm_cmd_press(&t.a, 5.0f, 0, &d) == ARM_REFUSE_RANGE && d == 1);
    CHECK(arm_cmd_press(&t.a, 5.0f, 20, &d) == ARM_OK && run_until_idle(&t, 20000));
    CHECK(t.done.status == ARM_DONE_COMPLETED);
    CHECK(t.done.values[0] >= 19.0f && t.done.values[0] < 30.0f); /* stopped at the force limit */
    CHECK(t.done.values[1] > 3.0f && t.done.values[1] < 4.5f);    /* depth where it stopped, not 5 mm */
    CHECK(sim_rig_pos(&t.rig, 8) < 1024.0 + 3.0 * 11.378);        /* retracted */
    /* A press that does not reach the button reports ~0 force. */
    CHECK(arm_cmd_press(&t.a, 2.0f, 50, &d) == ARM_OK && run_until_idle(&t, 20000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.done.values[0] < 1.0f);
    g_fsr_contact_enabled = 0;
}

static void test_cancel_tool_freezes(void) {
    tb t;
    uint8_t d = 0, m = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(arm_cmd_grip(&t.a, 60, 5, &d) == ARM_OK);
    run(&t, 100);
    CHECK(arm_stop(&t.a, &m) == ARM_STOP_INITIATED);
    run(&t, 100);
    {
        double g = sim_rig_reg16(&t.rig, 6, STS_REG_GOAL_POSITION), p = sim_rig_pos(&t.rig, 6);
        CHECK(fabs(g - p) < 2.0); /* goal rewritten to the measured position: the fingers stopped */
    }
}


/* ======================= Fix round 1 ======================================================== */

static float true_excess(tb *t);

/* Raw count of a joint angle under the nominal calibration. */
static int32_t nominal_raw(unsigned j, float deg) {
    arm_cal nom;
    int32_t raw = 0;
    arm_cal_nominal(&nom);
    CHECK(arm_to_raw(&nom, j, deg, &raw) == 0);
    return raw;
}

/* CRITICAL 1. A shoulder jammed at 90 deg while an accepted move drives the elbow toward 125 deg:
 * the commanded poses are all legal, the MEASURED pose is not. The arm must freeze at the measured
 * pose almost at once, fail with a distinct fault and refuse to carry on. */
static void test_jammed_joint_is_caught_on_the_measured_pose(void) {
    tb t;
    uint8_t d = 0;
    double elbow_goal_before;
    uint32_t t0;
    bring_up(&t);
    CHECK(move(&t, 0, 90, 60, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    sim_rig_jam(&t.rig, 2); /* the shoulder is obstructed where it stands */
    run(&t, 60);
    CHECK(move(&t, 0, 45, 125, 0, 0, 100, &d) == ARM_OK); /* every commanded waypoint is inside the limits */
    t0 = t.rig.now_ms;
    CHECK(run_until_idle(&t, 3000));
    CHECK(t.rig.now_ms - t0 < 500); /* not after a 3 s timeout */
    CHECK(t.done.status == ARM_DONE_FAILED);
    CHECK(t.done.fault == ARM_FAULT_FOLLOWING || t.done.fault == ARM_FAULT_LIMIT);
    CHECK(t.done.values[0] > 10.0f); /* the failed move reports its real error */
    CHECK(t.a.state == ARM_ST_FAULT && t.a.limit_latched && !t.a.traj_active);
    /* The elbow stopped well short of 125 deg and its goal was rewritten to where it was measured. */
    CHECK(joint_deg(&t, ARM_J_ELBOW) < 100.0f);
    elbow_goal_before = (double)sim_rig_reg16(&t.rig, 3, STS_REG_GOAL_POSITION);
    CHECK(fabs(sim_rig_pos(&t.rig, 3) - elbow_goal_before) < 60.0); /* goal rewritten to the measured pose */
    run(&t, 600);
    CHECK(fabs(sim_rig_pos(&t.rig, 3) - elbow_goal_before) < 12.0); /* and it settles and stays there */
    CHECK(t.a.torque_on && t.rig.servo_en_pin); /* holding, not dropped */
    /* Latched: nothing but a move back inside, enable or hold. */
    {
        uint8_t dd = 0;
        CHECK(arm_cmd_tool_mount(&t.a, &dd) == ARM_REFUSE_INHIBITED);
        CHECK(arm_cmd_release(&t.a, &dd) == ARM_REFUSE_INHIBITED);
    }
}

static void test_measured_limit_violation_without_following_error(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 80, 90, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000)); /* sum 170 */
    CHECK(move(&t, 0, 80, 94, 0, 0, 100, &d) == ARM_OK);                              /* sum 174: legal */
    run(&t, 40);
    /* The shoulder is pushed 12 deg beyond its waypoint (below the 15 deg following bound) while the
     * elbow moves on: measured shoulder + elbow = 184 deg > 175 + 4 slack. */
    sim_rig_place(&t.rig, 2, nominal_raw(ARM_J_SHOULDER, 92.0f));
    CHECK(run_until_idle(&t, 2000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_LIMIT);
    CHECK(t.a.move_limit == ARM_LIMIT_COUPLED_BASE + 0); /* forearm_pitch */
    CHECK(t.a.state == ARM_ST_FAULT);
}

static void test_lagging_joint_following_error(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    t.rig.sv[3].speed_scale = 0.08; /* a weak, sluggish elbow */
    CHECK(move(&t, 0, 40, 120, 0, 0, 100, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 4000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_FOLLOWING);
    CHECK(t.a.move_limit == ARM_J_ELBOW); /* the lagging joint is named */
    CHECK(t.a.state == ARM_ST_FAULT);
    CHECK(sim_rig_reg16(&t.rig, 3, STS_REG_GOAL_POSITION) < sim_rig_pos(&t.rig, 3) + 12.0); /* frozen near the measured pose */
}

static void test_recovery_from_a_latched_motion_fault(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 90, 60, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    sim_rig_jam(&t.rig, 2);
    run(&t, 60);
    CHECK(move(&t, 0, 45, 120, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(t.a.state == ARM_ST_FAULT);
    /* Still jammed: a recovery move is allowed to start but trips again (the shoulder cannot follow). */
    CHECK(move(&t, 0, 60, 60, 0, 0, 100, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 3000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.a.state == ARM_ST_FAULT && t.a.limit_latched);
    /* Free again: the move back inside runs, finishes and clears the latch. */
    t.rig.sv[2].block_lo = -1e9;
    t.rig.sv[2].block_hi = 1e9;
    CHECK(move(&t, 0, 60, 60, 0, 0, 100, &d) == ARM_OK && t.a.recovering);
    CHECK(run_until_idle(&t, 12000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.a.state == ARM_ST_READY && !t.a.limit_latched);
    CHECK(t.a.fault_code == ARM_FAULT_NONE);
    {
        const float want[5] = {0, 60, 60, 0, 0}; /* the MEASURED pose, not just the command */
        unsigned j;
        for (j = 0; j < 5; ++j) CHECK(fabsf(joint_deg(&t, j) - want[j]) < 2.5f);
        CHECK(true_excess(&t) == 0.0f);
    }
    CHECK(move(&t, 10, 50, 70, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000)); /* normal again */
}

/* IMPORTANT 5. Servo status error bits and over-temperature. */
static void test_servo_error_bits_and_overtemperature(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 60, 50, 70, 0, 0, 30, &d) == ARM_OK);
    run(&t, 150);
    t.rig.sv[3].err_bits = STS_ERR_OVERLOAD; /* the elbow servo reports an overload */
    CHECK(run_until_idle(&t, 500));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_SERVO_ERROR);
    CHECK(t.a.servo_err_id == 3 && t.a.servo_err_bits == STS_ERR_OVERLOAD);
    CHECK(t.a.state == ARM_ST_FAULT && !t.a.traj_active);
    {
        double p = sim_rig_pos(&t.rig, 1);
        run(&t, 300);
        CHECK(fabs(sim_rig_pos(&t.rig, 1) - p) < 12.0); /* frozen */
    }
    /* Over-temperature: warning at 60 C, motion refused at 70 C. */
    bring_up(&t);
    t.rig.sv[2].temp_c = 62;
    run(&t, 120);
    CHECK(arm_temperature_warning(&t.a) == 1);
    CHECK(move(&t, 10, 40, 60, 0, 0, 50, &d) == ARM_OK && run_until_idle(&t, 12000));
    t.rig.sv[2].temp_c = 71;
    run(&t, 120);
    CHECK(move(&t, 0, 40, 60, 0, 0, 50, &d) == ARM_REFUSE_INHIBITED && d == ARM_WHY_OVERTEMP);
    t.rig.sv[2].temp_c = 40;
    run(&t, 120);
    CHECK(move(&t, 0, 40, 60, 0, 0, 50, &d) == ARM_OK);
}

/* IMPORTANT 2. Controller reset by the watchdog. */

static void test_watchdog_reset_is_reported_and_needs_enable(void) {
    tb t;
    uint8_t d = 0;
    g_wdt = 1;
    tb_init(&t);
    g_wdt = 0;
    run(&t, 100);
    CHECK(t.a.watchdog_reset && t.a.fault_code == ARM_FAULT_WATCHDOG && t.a.pose_unknown);
    CHECK(t.a.state == ARM_ST_DISABLED && !t.rig.servo_en_pin && !t.a.torque_on); /* boot default */
    CHECK(move(&t, 0, 30, 90, 45, 0, 50, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NOT_ENABLED);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(t.a.state == ARM_ST_READY && t.a.fault_code == ARM_FAULT_NONE && !t.a.pose_unknown);
}

/* IMPORTANT 3. Absolute multi-turn mode and lost ACKs: a retried write must not repeat motion. */
static void test_lost_acks_never_duplicate_motion(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 3300.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK);
    t.rig.sv[7].drop_acks = 2; /* the torque-enable and goal-hold writes are applied, the ACKs lost */
    CHECK(run_until_idle(&t, 3000) && t.a.tool_state == TOOL_ST_READY);
    CHECK(fabs(sim_rig_pos(&t.rig, 7)) < 1.0); /* mounting moved nothing */
    /* turn(360): the torque-limit write and the goal write each lose their ACK and are retried. */
    t.rig.sv[7].drop_acks = 2;
    CHECK(arm_cmd_turn(&t.a, 360, 20, &d) == ARM_OK && run_until_idle(&t, 30000));
    CHECK(t.done.status == ARM_DONE_COMPLETED);
    CHECK(fabs(sim_rig_pos(&t.rig, 7) - 8192.0) < 20.0); /* one turn, not two */
    CHECK(fabsf(t.a.sv[ARM_S_KNOB].pos_deg - 360.0f) < 3.0f);
    /* Cancelling a tool motion rewrites the goal to the measured position: no further travel. */
    CHECK(arm_cmd_turn(&t.a, -300, 20, &d) == ARM_OK);
    run(&t, 1500);
    {
        uint8_t m = 0;
        double p;
        CHECK(arm_stop(&t.a, &m) == ARM_STOP_INITIATED);
        run(&t, 300);
        p = sim_rig_pos(&t.rig, 7);
        run(&t, 600);
        CHECK(fabs(sim_rig_pos(&t.rig, 7) - p) < 2.0);
    }
    /* The arm's own configuration writes survive lost ACKs (absolute, idempotent). */
    tb_init(&t);
    t.rig.sv[2].drop_acks = 2;
    t.rig.sv[4].drop_acks = 1;
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 5000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && sim_rig_reg16(&t.rig, 2, STS_REG_MAX_TORQUE) == 780);
}

/* IMPORTANT 4. Calibration. */
static void uncalibrated_tb(tb *t) {
    memset(t, 0, sizeof *t);
    sim_rig_init(&t->rig);
    t->sink.ctx = t;
    t->sink.finished = s_finished;
    t->sink.progress = s_progress;
    t->sink.stop_confirmed = s_stop;
    arm_init(&t->a, &t->rig.hw, 0, &t->sink); /* nothing stored: nominal zero, not calibrated */
}

static void test_calibration(void) {
    tb t;
    uint8_t d = 0;
    unsigned j;
    arm_cal nom;
    static const int off[5] = {0, 40, -25, 10, 0};
    uncalibrated_tb(&t);
    arm_cal_nominal(&nom);
    for (j = 0; j < 5; ++j) sim_rig_place(&t.rig, j + 1u, nominal_raw(j, kArmRestPose[j]) + off[j]);
    run(&t, 100);
    CHECK(!t.a.calibrated && t.a.state == ARM_ST_DISABLED);
    /* Limits are relative to the zero: no enable until it is known. */
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NOT_CALIBRATED);
    CHECK(!t.rig.servo_en_pin && !t.a.torque_on);
    CHECK(arm_cmd_calibrate(&t.a, &d) == ARM_OK && t.a.op == ARM_OP_CALIBRATE);
    CHECK(run_until_idle(&t, 6000));
    CHECK(t.done.kind == ARM_OP_CALIBRATE && t.done.status == ARM_DONE_COMPLETED);
    CHECK(t.a.calibrated && t.rig.cal_saves == 1);
    CHECK(t.rig.cal_saves_while_powered == 0); /* flash only with the rail off */
    CHECK(!t.rig.servo_en_pin && t.a.state == ARM_ST_DISABLED);
    for (j = 0; j < 5; ++j) {
        CHECK(sim_rig_reg8(&t.rig, j + 1u, STS_REG_TORQUE_ENABLE) == 0); /* nothing was ever torqued */
        CHECK(t.rig.saved_cal.raw_zero[j] == nom.raw_zero[j] + off[j]);
    }
    /* Reboot: the stored calibration is loaded and the measured rest pose reads exactly the rest pose. */
    arm_init(&t.a, &t.rig.hw, 0, &t.sink);
    run(&t, 100);
    CHECK(t.a.calibrated);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 5000));
    CHECK(t.done.status == ARM_DONE_COMPLETED);
    for (j = 0; j < 5; ++j) CHECK(fabsf(t.a.q_cmd.q[j] - kArmRestPose[j]) < 0.3f);
    CHECK(arm_cmd_calibrate(&t.a, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_NOT_DISABLED);
    /* A zero that would put a joint across the encoder wrap is refused and nothing is stored. */
    uncalibrated_tb(&t);
    sim_rig_place(&t.rig, 2, 3900.0);
    run(&t, 100);
    CHECK(arm_cmd_calibrate(&t.a, &d) == ARM_OK && run_until_idle(&t, 6000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_CALIBRATION);
    CHECK(!t.a.calibrated && t.rig.cal_saves == 0 && !t.rig.servo_en_pin && t.a.state == ARM_ST_DISABLED);
}

/* Enable-retry from a comm fault must not cut the rail that holds the arm. */
static void test_failed_reenable_keeps_the_rail(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    t.rig.drop_reply_mask = 1u << 3;
    run(&t, 400);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_SERVO_COMM);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 5000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_SERVO_COMM);
    CHECK(t.rig.servo_en_pin && t.rig.rail_mv > 11000 && t.rig.falls == 0); /* still powered, nothing fell */
    CHECK(sim_rig_reg8(&t.rig, 1, STS_REG_TORQUE_ENABLE) == 1);              /* the other joints still hold */
    CHECK(t.a.state == ARM_ST_FAULT);
}

static void test_press_timeout_retracts_and_fails(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 10000.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    t.rig.sv[8].block_hi = 1024.0 + 60.0; /* the cam is blocked 5 deg out: the depth is never reached */
    CHECK(arm_cmd_press(&t.a, 5.0f, 50, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 20000));
    CHECK(t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_TIMEOUT);
    t.rig.sv[8].block_hi = 1e9;
    run(&t, 1500);
    CHECK(sim_rig_pos(&t.rig, 8) < 1024.0 + 3.0 * 11.378); /* pulled back to the closed stop */
}

static void test_tool_swap_without_unmount(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000) && t.a.tool_state == TOOL_ST_READY);
    sim_rig_set_tool(&t.rig, 3300.0); /* swapped for another valid tool in one go */
    run(&t, 120);
    CHECK(!t.rig.tool_en_pin && t.a.tool_state == TOOL_ST_DETECTED && t.a.tool_id == ARM_TOOL_KNOB_TURNER);
    CHECK(arm_cmd_turn(&t.a, 10, 5, &d) == ARM_REFUSE_PRECONDITION && d == ARM_WHY_TOOL_NOT_READY);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000) && t.a.tool_state == TOOL_ST_READY);
}

static void test_millisecond_counter_wrap(void) {
    tb t;
    uint8_t d = 0;
    g_start_ms = 0xFFFFFF00u; /* a quarter second before the 32-bit counter wraps */
    tb_init(&t);
    g_start_ms = 0;
    run(&t, 50);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 5000));
    CHECK(t.done.status == ARM_DONE_COMPLETED);
    CHECK(move(&t, 30, 40, 60, 10, -20, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.rig.now_ms < 0x80000000u); /* the counter wrapped on the way */
    CHECK(t.a.state == ARM_ST_READY);
}

/* ======================= Fix round 2 ======================================================== */

static float g_max_excess;
static float true_excess(tb *t) {
    arm_pose p;
    uint8_t c;
    unsigned j;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) p.q[j] = joint_deg(t, j);
    return arm_pose_excess(&p, &c);
}
static void excess_hook(tb *t) {
    float e = true_excess(t);
    if (e > g_max_excess) g_max_excess = e;
}

/* C1-a. After a following/limit fault the same move is re-sent over and over (a client's natural
 * retry): every retry is "inside the limits" as commanded, but the jammed shoulder cannot follow.
 * The measured excess must never grow beyond the pre-retry value (plus one band of noise). */
static void retry_scenario(uint8_t pct) {
    tb t;
    uint8_t d = 0;
    float e0;
    unsigned k, refused = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 90, 60, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    sim_rig_jam(&t.rig, 2);
    run(&t, 60);
    CHECK(move(&t, 0, 45, 125, 0, 0, pct, &d) == ARM_OK);
    CHECK(run_until_idle(&t, 3000));
    CHECK(t.a.state == ARM_ST_FAULT && t.a.limit_latched);
    run(&t, 300);
    g_max_excess = 0.0f;
    excess_hook(&t);
    e0 = g_max_excess; /* measured excess before any retry */
    t.hook = excess_hook;
    for (k = 0; k < 8; ++k) {
        arm_refusal r = move(&t, 0, 45, 125, 0, 0, pct, &d);
        if (r != ARM_OK) {
            ++refused;
            CHECK(r == ARM_REFUSE_INHIBITED && d == ARM_WHY_RECOVERY_WORSE);
        }
        run(&t, 700);
        CHECK(t.a.state == ARM_ST_FAULT && t.a.torque_on);
    }
    CHECK(g_max_excess <= e0 + 3.0f); /* the original probe reached +38 deg */
    CHECK(refused >= 6);              /* after the first worsening nothing else is accepted */
    t.hook = 0;
}

static void test_retrying_a_jammed_move_does_not_ratchet(void) {
    retry_scenario(100);
    retry_scenario(50);
}

/* C1-b. The measured pose is checked while holding and during tool operations. */
static void test_displacement_while_holding_and_in_tool_ops(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 80, 90, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000)); /* forearm 170 */
    /* Someone pushes the shoulder to 97 deg while the arm holds: forearm 187 > 175. */
    sim_rig_place(&t.rig, 2, nominal_raw(ARM_J_SHOULDER, 97.0f));
    run(&t, 100);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_DISPLACED && t.a.limit_latched);
    CHECK(t.a.torque_on); /* still holding, frozen where it is */
    {
        double g = sim_rig_reg16(&t.rig, 2, STS_REG_GOAL_POSITION);
        run(&t, 300);
        /* it never travels further out (the servo-side 95 deg window may pull it back in) */
        CHECK(sim_rig_pos(&t.rig, 2) < g + 15.0);
    }
    CHECK(arm_cmd_hold(&t.a, &d) == ARM_OK); /* hold is accepted in a latched fault (INTERFACE.md 9.1) */
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_REFUSE_INHIBITED);
    /* Only a move back inside is allowed, and it must end measured inside. */
    CHECK(move(&t, 0, 60, 60, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.a.state == ARM_ST_READY && !t.a.limit_latched);
    CHECK(true_excess(&t) == 0.0f && fabsf(joint_deg(&t, ARM_J_SHOULDER) - 60.0f) < 2.5f);

    /* The same during a tool operation: it fails and the tool servo is frozen. */
    bring_up(&t);
    CHECK(move(&t, 0, 80, 90, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    sim_rig_set_tool(&t.rig, 1000.0);
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(arm_cmd_grip(&t.a, 60, 5, &d) == ARM_OK);
    run(&t, 60);
    sim_rig_place(&t.rig, 2, nominal_raw(ARM_J_SHOULDER, 97.0f));
    CHECK(run_until_idle(&t, 1000));
    CHECK(t.done.kind == ARM_OP_GRIP && t.done.status == ARM_DONE_FAILED && t.done.fault == ARM_FAULT_DISPLACED);
    CHECK(t.a.state == ARM_ST_FAULT);
    run(&t, 200);
    {
        double g = sim_rig_reg16(&t.rig, 6, STS_REG_GOAL_POSITION);
        CHECK(fabs(sim_rig_pos(&t.rig, 6) - g) < 15.0); /* the gripper stopped too */
    }
}

/* The freeze write is retried on a collision; when it cannot be confirmed the fault says so. */
static void test_freeze_write_is_retried_and_reported(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    CHECK(move(&t, 0, 80, 90, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    t.rig.corrupt_sync_n = 1; /* the first freeze write collides, the retry succeeds */
    sim_rig_place(&t.rig, 2, nominal_raw(ARM_J_SHOULDER, 97.0f));
    run(&t, 100);
    CHECK(t.a.fault_code == ARM_FAULT_DISPLACED && t.rig.corrupt_sync_n == 0);
    CHECK(fabs((double)sim_rig_reg16(&t.rig, 2, STS_REG_GOAL_POSITION) - sim_rig_pos(&t.rig, 2)) < 40.0);

    bring_up(&t);
    CHECK(move(&t, 0, 80, 90, 0, 0, 100, &d) == ARM_OK && run_until_idle(&t, 12000));
    t.rig.corrupt_sync_n = 100; /* every freeze attempt collides */
    sim_rig_place(&t.rig, 2, nominal_raw(ARM_J_SHOULDER, 97.0f));
    run(&t, 100);
    CHECK(t.a.state == ARM_ST_FAULT && t.a.fault_code == ARM_FAULT_BUS && t.a.limit_latched);
}

static void test_overtemperature_fault_clears_and_watchdog_report_clears(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    t.rig.sv[2].temp_c = 72;
    run(&t, 200);
    CHECK(t.a.fault_code == ARM_FAULT_OVERTEMP);
    t.rig.sv[2].temp_c = 40;
    run(&t, 200);
    CHECK(t.a.fault_code == ARM_FAULT_NONE); /* no sticky fault after cooling */
    CHECK(move(&t, 0, 40, 60, 0, 0, 50, &d) == ARM_OK);
    /* The watchdog report is cleared by the next successful enable (and by nothing else). */
    g_wdt = 1;
    tb_init(&t);
    g_wdt = 0;
    run(&t, 100);
    CHECK(t.a.watchdog_reset && t.a.fault_code == ARM_FAULT_WATCHDOG);
    CHECK(arm_cmd_enable(&t.a, &d) == ARM_OK && run_until_idle(&t, 4000));
    CHECK(!t.a.watchdog_reset && t.a.fault_code == ARM_FAULT_NONE);
}

/* The knob goal is the mount position plus the turn: it must stay inside the +-7 servo turns. */
static void test_knob_range_includes_the_mount_offset(void) {
    tb t;
    uint8_t d = 0;
    bring_up(&t);
    sim_rig_set_tool(&t.rig, 3300.0);
    sim_rig_place(&t.rig, 7, 8000.0); /* the knob was left 8000 counts from zero */
    run(&t, 150);
    CHECK(arm_cmd_tool_mount(&t.a, &d) == ARM_OK && run_until_idle(&t, 3000));
    CHECK(t.a.knob_zero_steps == 8000);
    CHECK(arm_cmd_turn(&t.a, 1000, 10, &d) == ARM_REFUSE_RANGE && d == 0); /* 8000 + 22 756 > 28 000 */
    CHECK(arm_cmd_turn(&t.a, -500, 10, &d) == ARM_OK);                     /* inside */
    run_until_idle(&t, 60000);
    CHECK(arm_cmd_turn(&t.a, 500, 10, &d) == ARM_OK);
}

int main(void) {
    test_boot_states();
    test_enable_sequence();
    test_enable_failures();
    test_move_in_limits();
    test_limit_refusals();
    test_waypoint_layer_is_independent();
    test_estop_in_motion();
    test_estop_contact_fault();
    test_rail_faults();
    test_home_and_release();
    test_hold_cancel_and_stop();
    test_servo_lost_and_bus_collision();
    test_tools();
    test_tool_hot_unplug_and_estop();
    test_knob_and_presser();
    test_cancel_tool_freezes();
    test_jammed_joint_is_caught_on_the_measured_pose();
    test_measured_limit_violation_without_following_error();
    test_lagging_joint_following_error();
    test_recovery_from_a_latched_motion_fault();
    test_servo_error_bits_and_overtemperature();
    test_watchdog_reset_is_reported_and_needs_enable();
    test_lost_acks_never_duplicate_motion();
    test_calibration();
    test_failed_reenable_keeps_the_rail();
    test_press_timeout_retracts_and_fails();
    test_tool_swap_without_unmount();
    test_millisecond_counter_wrap();
    test_retrying_a_jammed_move_does_not_ratchet();
    test_displacement_while_holding_and_in_tool_ops();
    test_freeze_write_is_retried_and_reported();
    test_overtemperature_fault_clears_and_watchdog_report_clears();
    test_knob_range_includes_the_mount_offset();
    TEST_FINISH("test_arm");
}
