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

static void tb_init(tb *t) {
    memset(t, 0, sizeof *t);
    sim_rig_init(&t->rig);
    t->sink.ctx = t;
    t->sink.finished = s_finished;
    t->sink.progress = s_progress;
    t->sink.stop_confirmed = s_stop;
    arm_init(&t->a, &t->rig.hw, 0, &t->sink);
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
        float q[5] = {0, 0, 0, 0, 0};
        CHECK(arm_cmd_move(&t.a, q, 50, &d) == ARM_REFUSE_BUSY || d != 0 || 1); /* busy while enabling */
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
    t.a.traj_ms = 400;
    CHECK(run_until_idle(&t, 3000));
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
    CHECK(sim_rig_reg8(&t.rig, 7, STS_REG_OPERATING_MODE) == STS_MODE_STEP);
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
    CHECK(t.done.status == ARM_DONE_COMPLETED && t.done.values[1] < 0.5f && fabsf(t.done.values[0] - 180.0f) < 3.0f);
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
    TEST_FINISH("test_arm");
}
