#include "arm.h"

#include <math.h>
#include <string.h>

#define kPi 3.14159265358979f
#define kRadToDeg (180.0f / kPi)
#define kDegToRad (kPi / 180.0f)

enum {
    kTrajMs = 20u,          /* waypoint period while a motion runs */
    kScanMs = 5u,           /* one telemetry block read per period, round robin */
    kInaMs = 10u,
    kVinMs = 50u,
    kServoBootMs = 300u,    /* servos reboot when the rail returns */
    kSettleTimeoutMs = 3000u,
    kScanStaleMs = 500u,
    kCommFailLimit = 5u,
    kToolPowerMs = 50u,     /* INTERFACE.md section 5: wait after TOOL_EN */
    kToolDischargeMs = 60u, /* >= 50 ms before the unlocking roll */
    kToolOpTimeoutMs = 5000u,
    kStallMs = 250u,
    kGoalWraps = 100 /* write_arm_goals: the goal would wrap through the encoder boundary */
};
#define kSettleTolDeg 2.0f
#define kFollowErrDeg 15.0f   /* measured pose may trail the commanded waypoint by at most this */
#define kMeasSlackDeg 4.0f    /* limit slack on a measured pose (encoder noise, servo lag) */
#define kGuardStaleMs 200u
#define kTempWarnC 60u
#define kHomeSpeedCapPct 30u
#define kTempFaultC 70u

/* ---- Small helpers ------------------------------------------------------------- */
static uint8_t servo_id(unsigned s) { return kArmServos[s].servo_id; }

/* Wrap-safe: true when time stamp `a` is earlier than `b` (the millisecond counter wraps). */
static int before(uint32_t a, uint32_t b) { return (int32_t)(a - b) < 0; }

static int write_arm_goals(arm *a, const arm_pose *q);

static unsigned tool_servo_index(uint8_t tool_code) {
    switch (tool_code) {
    case ARM_TOOL_GRIPPER: return ARM_S_GRIPPER;
    case ARM_TOOL_KNOB_TURNER: return ARM_S_KNOB;
    case ARM_TOOL_BUTTON_PRESSER: return ARM_S_PRESSER;
    default: return ARM_NUM_SERVOS; /* the slider pusher is passive */
    }
}

int arm_servos_powered(const arm *a) {
    return a->pwr.state == PWR_ON && !a->pwr.latched && a->ina_ok && a->rail_mv >= PWR_RAIL_OK_MV;
}

static float worst_joint_error(const arm *a) {
    unsigned j;
    float worst = 0.0f;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float e = fabsf(a->sv[j].pos_deg - a->q_goal.q[j]);
        if (a->sv[j].valid && e > worst) worst = e;
    }
    return worst;
}

static void finish(arm *a, uint8_t status, uint8_t fault, uint8_t measured, float v0, float v1,
                   float v2) {
    arm_completion d;
    d.kind = a->op;
    if (a->op == ARM_OP_MOVE || a->op == ARM_OP_HOME || a->op == ARM_OP_RELEASE) {
        float err = worst_joint_error(a);
        a->last_move_err = err;
        if (status != ARM_DONE_COMPLETED) v0 = err; /* a failed move still reports the real error */
    }
    d.status = status;
    d.fault = fault;
    d.measured = measured;
    d.values[0] = v0;
    d.values[1] = v1;
    d.values[2] = v2;
    a->op = ARM_OP_NONE;
    a->op_step = 0;
    a->traj_active = 0;
    if (a->state == ARM_ST_MOVING || a->state == ARM_ST_ENABLING) a->state = ARM_ST_READY;
    if (a->recovering) {
        a->recovering = 0;
        if (status == ARM_DONE_COMPLETED) { /* moved back inside the limits: the latch clears */
            a->limit_latched = 0;
            a->fault_code = ARM_FAULT_NONE;
        } else if (a->limit_latched) {
            a->state = ARM_ST_FAULT;
        }
    }
    if (a->sink != 0 && a->sink->finished != 0) a->sink->finished(a->sink->ctx, &d);
}

static void bus_note(arm *a, int rc) {
    if (rc == STSB_COLLISION) a->bus_fail = (uint8_t)(a->bus_fail < 255u ? a->bus_fail + 1u : 255u);
    else if (rc == STSB_OK) a->bus_fail = 0;
}

/* ---- Power sampling and reaction ------------------------------------------------ */
static void power_step(arm *a, uint32_t now, int force) {
    power_in in;
    in.now_ms = now;
    in.sense = a->hw->estop_sense(a->hw->ctx) ? 1u : 0u;
    in.edge = a->hw->estop_take_edge(a->hw->ctx) ? 1u : 0u;
    if (force || (uint32_t)(now - a->last_ina_ms) >= kInaMs) {
        uint16_t bus_reg = 0;
        int16_t cur_reg = 0;
        a->last_ina_ms = now;
        if (a->hw->ina_read(a->hw->ctx, &bus_reg, &cur_reg) == 0) {
            a->ina_ok = 1;
            a->rail_mv = ina219_bus_mv(bus_reg);
            a->rail_ma = ina219_current_ma(cur_reg);
        } else {
            a->ina_ok = 0;
        }
    }
    if (force || (uint32_t)(now - a->last_vin_ms) >= kVinMs) {
        a->last_vin_ms = now;
        a->vin_mv = power_vin_mv(a->hw->adc_read(a->hw->ctx, ARM_ADC_VIN));
    }
    a->sense = in.sense;
    in.ina_ok = a->ina_ok;
    in.rail_mv = a->rail_mv;
    in.rail_ma = a->rail_ma;
    in.vin_mv = a->vin_mv;
    power_update(&a->pwr, &in);
    if (a->pwr.rail_cmd != a->rail_applied || !a->pwr.rail_cmd) {
        a->hw->servo_en(a->hw->ctx, a->pwr.rail_cmd);
        a->rail_applied = a->pwr.rail_cmd;
    }
}

static void tool_off(arm *a) {
    a->hw->tool_en(a->hw->ctx, 0);
    a->tool_state = a->tool_id >= 1u && a->tool_id <= 4u ? TOOL_ST_DETECTED : TOOL_ST_NONE;
}

/* The arm lost its rail (E-stop) or a hardware fault cut it: nothing is held any more. */
static void react_power(arm *a, uint32_t now) {
    arm_state want = ARM_ST_BOOT;
    (void)now;
    if (a->pwr.hard_fault) want = ARM_ST_FAULT;
    else if (a->pwr.latched) want = ARM_ST_ESTOP;
    else if (a->pwr.state == PWR_FAULT) want = ARM_ST_FAULT;
    if (want == ARM_ST_BOOT || a->state == want) return;
    a->fault_code = a->pwr.fault;
    a->torque_on = 0;
    a->pose_unknown = 1; /* "arm may have moved: re-home before use" */
    a->traj_active = 0;
    a->freeze_servo = 0;
    if (a->tool_state != TOOL_ST_NONE) tool_off(a);
    a->state = want;
    if (a->op != ARM_OP_NONE) finish(a, ARM_DONE_FAILED, a->fault_code, 1, 0, 0, 0);
    a->state = want; /* finish() must not leave it READY */
}

/* ---- Telemetry ------------------------------------------------------------------ */
static int telemetry_read(arm *a, unsigned s, uint32_t now) {
    uint8_t b[STS_TELEMETRY_LEN], err = 0;
    arm_servo_state *v = &a->sv[s];
    int rc = sts_bus_read(&a->bus, servo_id(s), STS_REG_PRESENT_POSITION, STS_TELEMETRY_LEN, b, &err);
    bus_note(a, rc);
    if (rc != STSB_OK) {
        if (v->fail_count < 255u) ++v->fail_count;
        return rc;
    }
    v->fail_count = 0;
    v->valid = 1;
    v->error = err;
    v->stamp_ms = now;
    if (s == ARM_S_KNOB) {
        int32_t steps = sts_sm_decode(sts_get16(&b[0]), 15);
        v->raw_steps = steps;
        v->pos_deg = (float)(steps - a->knob_zero_steps) * 360.0f / ARM_SERVO_COUNTS /
                     kArmServos[s].ratio;
    } else {
        v->raw_steps = (int32_t)(sts_get16(&b[0]) & 0x0FFFu);
        v->pos_deg = arm_from_raw(&a->cal, s, v->raw_steps);
    }
    v->speed_dps = (float)sts_sm_decode(sts_get16(&b[2]), 15) * 360.0f / ARM_SERVO_COUNTS /
                   kArmServos[s].ratio;
    v->load_permille = (int16_t)sts_sm_decode(sts_get16(&b[4]), 10);
    v->volt_dv = b[6];
    v->temp_c = b[7];
    v->moving = b[0x42 - 0x38];
    v->current_ma = (uint16_t)(((uint32_t)sts_get16(&b[0x45 - 0x38]) * 13u) / 2u); /* 6.5 mA/LSB */
    return STSB_OK;
}

static int scan_eligible(const arm *a, unsigned s) {
    if (s < ARM_NUM_JOINTS) return 1;
    return a->tool_state == TOOL_ST_READY && tool_servo_index(a->tool_id) == s;
}

static void servo_lost(arm *a, unsigned s) {
    if (s < ARM_NUM_JOINTS) {
        a->fault_code = ARM_FAULT_SERVO_COMM;
        a->state = ARM_ST_FAULT; /* the rail stays on: the servos that still answer hold */
        a->traj_active = 0;
        if (a->op != ARM_OP_NONE) finish(a, ARM_DONE_FAILED, ARM_FAULT_SERVO_COMM, 0, 0, 0, 0);
        a->state = ARM_ST_FAULT;
    } else {
        a->hw->tool_en(a->hw->ctx, 0);
        a->tool_state = TOOL_ST_LOST;
        a->fault_code = ARM_FAULT_TOOL;
        if (a->op >= ARM_OP_GRIP || a->op == ARM_OP_TOOL_MOUNT)
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL, 0, 0, 0, 0);
    }
}

/* Servo status-packet error bits that mean the joint is in trouble. The angle bit is not one:
 * it only says the servo-side window rejected a goal, which the firmware never sends. */
#define kFatalServoErr \
    (STS_ERR_VOLTAGE | STS_ERR_SENSOR | STS_ERR_TEMPERATURE | STS_ERR_CURRENT | STS_ERR_OVERLOAD)

static void write_freeze_at_measured(arm *a) {
    arm_pose m;
    unsigned j;
    uint32_t now = a->hw->millis(a->hw->ctx);
    /* The cached samples are up to one scan period old and a joint moves meanwhile: read fresh. */
    for (j = 0; j < ARM_NUM_JOINTS; ++j) (void)telemetry_read(a, j, now);
    for (j = 0; j < ARM_NUM_JOINTS; ++j) m.q[j] = a->sv[j].valid ? a->sv[j].pos_deg : a->q_cmd.q[j];
    if (write_arm_goals(a, &m) == STSB_OK) a->q_cmd = m;
}

/* Freeze where the arm is (goal = measured), end the operation, latch a recoverable fault. */
static void trip(arm *a, uint8_t fault, uint8_t limit_code) {
    write_freeze_at_measured(a);
    a->traj_active = 0;
    a->move_limit = limit_code;
    a->limit_latched = 1;
    a->fault_code = fault;
    a->state = ARM_ST_FAULT;
    if (a->op != ARM_OP_NONE) finish(a, ARM_DONE_FAILED, fault, 1, 0, 0, 0);
    a->state = ARM_ST_FAULT;
}

static void servo_error_check(arm *a, unsigned s) {
    uint8_t bits = (uint8_t)(a->sv[s].error & kFatalServoErr);
    if (s >= ARM_NUM_JOINTS || bits == 0 || !a->torque_on) return;
    if (a->state != ARM_ST_READY && a->state != ARM_ST_MOVING) return;
    a->servo_err_id = servo_id(s);
    a->servo_err_bits = bits;
    trip(a, ARM_FAULT_SERVO_ERROR, ARM_LIMIT_NONE);
}

static void scan_step(arm *a, uint32_t now) {
    unsigned tries, s;
    if (!arm_servos_powered(a) || a->op == ARM_OP_ENABLE || a->op == ARM_OP_CALIBRATE ||
        a->op == ARM_OP_TOOL_MOUNT)
        return;
    if (a->state != ARM_ST_READY && a->state != ARM_ST_MOVING && a->state != ARM_ST_PARKED &&
        a->state != ARM_ST_FAULT)
        return;
    if ((uint32_t)(now - a->last_scan_ms) < kScanMs) return;
    a->last_scan_ms = now;
    for (tries = 0; tries < ARM_NUM_SERVOS; ++tries) {
        s = a->scan_next;
        a->scan_next = (uint8_t)((a->scan_next + 1u) % ARM_NUM_SERVOS);
        if (!scan_eligible(a, s)) continue;
        if (telemetry_read(a, s, now) != STSB_OK) {
            if (a->sv[s].fail_count >= kCommFailLimit) servo_lost(a, s);
        } else {
            if (a->sv[s].temp_c >= kTempFaultC && a->fault_code == ARM_FAULT_NONE)
                a->fault_code = ARM_FAULT_OVERTEMP; /* warning; motion is refused while hot */
            servo_error_check(a, s);
        }
        return;
    }
}

/* ---- Servo configuration (EEPROM limits, torque cap, mode), read back to verify ----- */
typedef struct {
    uint16_t rdt, min_raw, max_raw, max_torque;
    uint8_t mode;
} cfg_target;

static int cfg_targets(const arm *a, unsigned s, cfg_target *t) {
    int32_t lo, hi;
    t->rdt = 0;
    t->max_torque = kArmServos[s].torque_permille;
    t->mode = STS_MODE_POSITION; /* the knob is multi-turn absolute: position mode, window 0..0 */
    if (s == ARM_S_KNOB) { /* multi-turn: no servo-side angle window */
        t->min_raw = t->max_raw = 0;
        return 0;
    }
    if (arm_to_raw(&a->cal, s, kArmServos[s].lo_deg, &lo) != 0 ||
        arm_to_raw(&a->cal, s, kArmServos[s].hi_deg, &hi) != 0)
        return -1;
    t->min_raw = (uint16_t)(lo < hi ? lo : hi);
    t->max_raw = (uint16_t)(lo < hi ? hi : lo);
    return 0;
}

/* Returns 0 while working, 1 when servo `s` is configured and verified, -1 on failure. */
static int cfg_run(arm *a, unsigned s) {
    cfg_target t;
    uint8_t buf[27], v[4];
    int rc = STSB_OK;
    uint8_t id = servo_id(s);
    if (cfg_targets(a, s, &t) != 0) return -1;
    switch (a->cfg_phase) {
    case 0: { /* read Return_Delay .. Operating_Mode (0x07..0x21) and compare */
        int match;
        rc = sts_bus_read(&a->bus, id, STS_REG_RETURN_DELAY, sizeof buf, buf, 0);
        if (rc != STSB_OK) break;
        match = buf[0] == t.rdt && sts_get16(&buf[STS_REG_MIN_ANGLE - STS_REG_RETURN_DELAY]) == t.min_raw &&
                sts_get16(&buf[STS_REG_MAX_ANGLE - STS_REG_RETURN_DELAY]) == t.max_raw &&
                sts_get16(&buf[STS_REG_MAX_TORQUE - STS_REG_RETURN_DELAY]) == t.max_torque &&
                buf[STS_REG_OPERATING_MODE - STS_REG_RETURN_DELAY] == t.mode;
        if (match) a->cfg_phase = 7;
        else if (a->cfg_verify) return -1; /* programmed, but it does not read back */
        else a->cfg_phase = 1;
        return 0;
    }
    case 1: v[0] = 0; rc = sts_bus_write(&a->bus, id, STS_REG_LOCK, v, 1); break;
    case 2: v[0] = (uint8_t)t.rdt; rc = sts_bus_write(&a->bus, id, STS_REG_RETURN_DELAY, v, 1); break;
    case 3:
        sts_put16(&v[0], t.min_raw);
        sts_put16(&v[2], t.max_raw);
        rc = sts_bus_write(&a->bus, id, STS_REG_MIN_ANGLE, v, 4);
        break;
    case 4:
        sts_put16(v, t.max_torque);
        rc = sts_bus_write(&a->bus, id, STS_REG_MAX_TORQUE, v, 2);
        break;
    case 5: v[0] = t.mode; rc = sts_bus_write(&a->bus, id, STS_REG_OPERATING_MODE, v, 1); break;
    case 6:
        v[0] = 1;
        rc = sts_bus_write(&a->bus, id, STS_REG_LOCK, v, 1);
        if (rc == STSB_OK) {
            a->cfg_verify = 1;
            a->cfg_phase = 0;
            a->cfg_retry = 0;
            return 0;
        }
        break;
    default: /* 7: RAM torque limit, same cap as the EEPROM value */
        sts_put16(v, t.max_torque);
        rc = sts_bus_write(&a->bus, id, STS_REG_TORQUE_LIMIT, v, 2);
        if (rc == STSB_OK) {
            a->cfg_phase = 0;
            a->cfg_verify = 0;
            a->cfg_retry = 0;
            return 1;
        }
        break;
    }
    bus_note(a, rc);
    if (rc != STSB_OK) {
        if (++a->cfg_retry >= 3u) return -1;
        return 0;
    }
    a->cfg_retry = 0;
    ++a->cfg_phase;
    return 0;
}

static void cfg_reset(arm *a) { a->cfg_phase = 0; a->cfg_verify = 0; a->cfg_retry = 0; }

/* ---- Goal writes ------------------------------------------------------------------ */
static int write_arm_goals(arm *a, const arm_pose *q) {
    uint8_t ids[ARM_NUM_JOINTS], data[ARM_NUM_JOINTS * 7u];
    unsigned j;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        int32_t raw;
        uint8_t *d = &data[j * 7u];
        if (arm_to_raw(&a->cal, j, q->q[j], &raw) != 0) return kGoalWraps;
        ids[j] = servo_id(j);
        d[0] = 0; /* acceleration: servo default profile; the trajectory shapes the motion */
        sts_put16(&d[1], (uint16_t)raw);
        sts_put16(&d[3], 0);
        sts_put16(&d[5], a->servo_speed_steps);
    }
    {
        int rc = sts_bus_sync_write(&a->bus, STS_REG_ACCELERATION, 7, ARM_NUM_JOINTS, ids, data);
        bus_note(a, rc);
        return rc;
    }
}

static int write_torque(arm *a, uint8_t on) {
    uint8_t ids[ARM_NUM_JOINTS], data[ARM_NUM_JOINTS];
    unsigned j;
    int rc;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        ids[j] = servo_id(j);
        data[j] = on;
    }
    rc = sts_bus_sync_write(&a->bus, STS_REG_TORQUE_ENABLE, 1, ARM_NUM_JOINTS, ids, data);
    bus_note(a, rc);
    return rc;
}

/* Goal for a tool servo in its own units (servo degrees; knob: signed steps). */
static int write_tool_goal(arm *a, unsigned s, int32_t raw_or_steps, uint16_t speed) {
    uint8_t d[7];
    uint16_t pos = s == ARM_S_KNOB ? sts_sm_encode(raw_or_steps, 15) : (uint16_t)raw_or_steps;
    int rc;
    d[0] = 0;
    sts_put16(&d[1], pos);
    sts_put16(&d[3], 0);
    sts_put16(&d[5], speed);
    rc = sts_bus_write(&a->bus, servo_id(s), STS_REG_ACCELERATION, d, sizeof d);
    bus_note(a, rc);
    return rc;
}

static int write_tool_torque_limit(arm *a, unsigned s, uint16_t permille) {
    uint8_t d[2];
    int rc;
    sts_put16(d, permille);
    rc = sts_bus_write(&a->bus, servo_id(s), STS_REG_TORQUE_LIMIT, d, 2);
    bus_note(a, rc);
    return rc;
}

static int write_tool_torque_enable(arm *a, unsigned s, uint8_t on) {
    int rc = sts_bus_write(&a->bus, servo_id(s), STS_REG_TORQUE_ENABLE, &on, 1);
    bus_note(a, rc);
    return rc;
}

/* ---- Lifecycle ------------------------------------------------------------------- */
void arm_init(arm *a, const arm_hw *hw, const arm_cal *cal, const arm_sink *sink) {
    memset(a, 0, sizeof *a);
    a->hw = hw;
    a->sink = sink;
    sts_bus_init(&a->bus, hw);
    arm_cal_nominal(&a->cal);
    if (cal != 0) {
        a->cal = *cal;
        a->calibrated = 1;
    } else if (hw->cal_load != 0 && hw->cal_load(hw->ctx, &a->cal)) {
        a->calibrated = 1;
    } else {
        arm_cal_nominal(&a->cal); /* assumed zero: motion stays refused until calibrated */
    }
    if (hw->watchdog_reset != 0 && hw->watchdog_reset(hw->ctx)) {
        /* The controller reset itself: servo power dropped and the arm may have fallen. The boot
         * default (rail off, explicit enable) applies; the cause stays visible until an enable. */
        a->watchdog_reset = 1;
        a->fault_code = ARM_FAULT_WATCHDOG;
    }
    power_init(&a->pwr);
    tool_id_init(&a->tid);
    a->state = ARM_ST_BOOT;
    a->pose_unknown = 1;
    a->tool_id = ARM_TOOL_NONE;
    /* Reset defaults (INTERFACE.md section 2): rail and tool power off. Assert them. */
    hw->servo_en(hw->ctx, 0);
    hw->tool_en(hw->ctx, 0);
    a->rail_applied = 0;
    /* Sample the supply and the rail at the first tick, not one period later. */
    a->last_ina_ms = 0u - kInaMs;
    a->last_vin_ms = 0u - kVinMs;
}

/* ---- Tool identity and power -------------------------------------------------------- */
static void tool_step(arm *a, uint32_t now) {
    uint16_t code = a->hw->adc_read(a->hw->ctx, ARM_ADC_TOOL_ID);
    uint8_t prev_id;
    if (!tool_id_update(&a->tid, now, code)) return;
    prev_id = a->tool_id;
    a->tool_id = a->tid.stable;
    if (a->tool_id != ARM_TOOL_NONE && prev_id != ARM_TOOL_NONE && prev_id != a->tool_id &&
        (a->tool_state == TOOL_ST_POWERING || a->tool_state == TOOL_ST_READY ||
         a->tool_state == TOOL_ST_UNMOUNTING)) {
        /* A different tool appeared without an unmount: whatever was configured is wrong for
         * it. Power it down; it must be mounted again (re-armed) before any tool action. */
        a->hw->tool_en(a->hw->ctx, 0);
        a->tool_state = TOOL_ST_DETECTED;
        a->fault_code = ARM_FAULT_TOOL;
        if (a->op == ARM_OP_TOOL_MOUNT || a->op >= ARM_OP_GRIP)
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL, 1, 0, 0, 0);
        return;
    }
    if (a->tool_id == ARM_TOOL_NONE) {
        if (a->tool_state == TOOL_ST_POWERING || a->tool_state == TOOL_ST_READY ||
            a->tool_state == TOOL_ST_UNMOUNTING) {
            /* Hot unplug while powered: clear TOOL_EN at once and report tool_lost. */
            a->hw->tool_en(a->hw->ctx, 0);
            a->tool_state = TOOL_ST_LOST;
            a->fault_code = ARM_FAULT_TOOL_LOST;
            if (a->op == ARM_OP_TOOL_MOUNT || a->op >= ARM_OP_GRIP)
                finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL_LOST, 1, 0, 0, 0);
        } else if (a->tool_state != TOOL_ST_LOST) {
            a->tool_state = TOOL_ST_NONE;
        }
    } else if (a->tool_state == TOOL_ST_NONE || a->tool_state == TOOL_ST_LOST) {
        a->tool_state = TOOL_ST_DETECTED;
    }
}

/* ---- Trajectories ---------------------------------------------------------------- */
/* Measured pose of the five joints when every sample is fresh (and newer than `since`). */
static int fresh_pose(const arm *a, arm_pose *m, uint32_t now, uint32_t since, int use_since) {
    unsigned j;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        if (!a->sv[j].valid || (uint32_t)(now - a->sv[j].stamp_ms) > kGuardStaleMs) return 0;
        if (use_since && before(a->sv[j].stamp_ms, since)) return 0;
        m->q[j] = a->sv[j].pos_deg;
    }
    return 1;
}

/* A new motion starts from where the arm actually is when that diverges from the last command
 * (a joint was pushed, jammed or lagged): waypoints and limit checks then relate to the real pose. */
static void sync_cmd_to_measured(arm *a, uint32_t now) {
    arm_pose m;
    unsigned j;
    int diverged = 0;
    if (!fresh_pose(a, &m, now, 0, 0)) return;
    for (j = 0; j < ARM_NUM_JOINTS; ++j)
        if (fabsf(m.q[j] - a->q_cmd.q[j]) > 2.0f) diverged = 1;
    if (diverged) a->q_cmd = m;
}

static void traj_start(arm *a, const arm_pose *goal, uint32_t pct, arm_op_kind kind, uint32_t now) {
    unsigned j;
    float t_ms = 0.0f;
    a->recovering = (a->state == ARM_ST_FAULT && a->limit_latched) ? 1u : 0u;
    sync_cmd_to_measured(a, now);
    {
        /* Starting outside a limit (moved by hand, pushed): only a move back inside is allowed, so
         * the measured-pose limit check is off for this motion; the waypoint check still keeps it
         * from getting worse and the following-error bound still applies. */
        arm_pose m;
        if (fresh_pose(a, &m, now, 0, 0) && arm_check_pose(&m, -kMeasSlackDeg) != ARM_LIMIT_NONE)
            a->recovering = 1;
    }
    a->q_start = a->q_cmd;
    a->q_goal = *goal;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float d = fabsf(goal->q[j] - a->q_cmd.q[j]);
        float v = arm_speed_limit_dps(j) * (float)pct / 100.0f;
        /* smoothstep peaks at 1.5x the mean speed, so scale the duration to keep the peak
         * at the commanded fraction of the speed limit. */
        float t = 1.5f * d / v * 1000.0f;
        if (t > t_ms) t_ms = t;
    }
    if (t_ms < 100.0f) t_ms = 100.0f;
    a->traj_ms = (uint32_t)t_ms + 1u;
    a->traj_t0 = now;
    a->traj_last_ms = now - kTrajMs;
    a->traj_active = 1;
    a->last_progress = 0;
    a->progress_ms = now;
    a->servo_speed_steps = (uint16_t)(3064.0f * (float)pct / 100.0f * 1.25f + 100.0f);
    a->op = kind;
    a->op_step = 0;
    a->state = ARM_ST_MOVING;
}

static void traj_tick(arm *a, uint32_t now) {
    float tau, s;
    arm_pose q;
    unsigned j;
    uint8_t lim;
    int rc;
    if ((uint32_t)(now - a->traj_last_ms) < kTrajMs) return;
    tau = (float)(now - a->traj_t0) / (float)a->traj_ms;
    if (tau > 1.0f) tau = 1.0f;
    s = tau * tau * (3.0f - 2.0f * tau);
    for (j = 0; j < ARM_NUM_JOINTS; ++j)
        q.q[j] = tau >= 1.0f ? a->q_goal.q[j]
                             : a->q_start.q[j] + s * (a->q_goal.q[j] - a->q_start.q[j]);
    /* Independent layer: every waypoint is checked against the same limits as the goal. */
    lim = arm_check_step(&a->q_cmd, &q);
    if (lim != ARM_LIMIT_NONE) {
        a->move_limit = lim;
        a->traj_active = 0; /* freeze at the last good waypoint (the servos hold it) */
        finish(a, ARM_DONE_FAILED, ARM_FAULT_LIMIT, 0, 0, 0, 0);
        return;
    }
    rc = write_arm_goals(a, &q);
    if (rc != STSB_OK) {
        a->traj_last_ms = now;
        if (a->bus_fail >= 3u || rc == kGoalWraps) {
            a->traj_active = 0;
            finish(a, ARM_DONE_FAILED, rc == kGoalWraps ? ARM_FAULT_LIMIT : ARM_FAULT_BUS, 0, 0, 0, 0);
        }
        return;
    }
    a->q_cmd = q;
    a->traj_last_ms = now;
    {
        uint8_t pct = (uint8_t)(tau * 100.0f);
        if (a->sink != 0 && a->sink->progress != 0 && pct >= a->last_progress + 10u &&
            (uint32_t)(now - a->progress_ms) >= 200u && a->op == ARM_OP_MOVE) {
            a->last_progress = pct;
            a->progress_ms = now;
            a->sink->progress(a->sink->ctx, pct);
        }
    }
    if (tau >= 1.0f) {
        a->traj_active = 0;
        a->op_step = 1; /* settle */
        a->op_t0 = now;
    }
}

/* Settled: every arm servo read after the trajectory ended, within tolerance and stopped. */
static int settled(arm *a, float *max_err) {
    unsigned j;
    float worst = 0.0f;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float e;
        if (!a->sv[j].valid || before(a->sv[j].stamp_ms, a->op_t0)) return 0;
        e = fabsf(a->sv[j].pos_deg - a->q_goal.q[j]);
        if (e > worst) worst = e;
        if (e > kSettleTolDeg || a->sv[j].moving) return 0;
    }
    *max_err = worst;
    return 1;
}

/* Limits on the MEASURED pose while moving (the command checks only see what was asked for): a
 * jammed or lagging joint can drive another into a coupled limit. On the first fresh sample that
 * violates a limit (with slack) or trails its waypoint by more than the following-error bound,
 * freeze at the measured pose, fail the motion and latch until an explicit recovery. */
static void motion_guard(arm *a, uint32_t now) {
    arm_pose m;
    unsigned j;
    uint8_t lim;
    if (!a->torque_on || a->op == ARM_OP_NONE || !fresh_pose(a, &m, now, a->traj_t0, 1)) return;
    for (j = 0; j < ARM_NUM_JOINTS; ++j)
        if (fabsf(m.q[j] - a->q_cmd.q[j]) > kFollowErrDeg) {
            trip(a, ARM_FAULT_FOLLOWING, (uint8_t)j);
            return;
        }
    if (!a->recovering) {
        lim = arm_check_pose(&m, -kMeasSlackDeg);
        if (lim != ARM_LIMIT_NONE) trip(a, ARM_FAULT_LIMIT, lim);
    }
}

static void move_step(arm *a, uint32_t now) {
    motion_guard(a, now);
    if (a->op == ARM_OP_NONE) return;
    if (a->traj_active) {
        traj_tick(a, now);
        return;
    }
    if (a->op == ARM_OP_NONE) return; /* finished inside traj_tick */
    {
        float err = 0.0f;
        if (settled(a, &err)) {
            if (a->op == ARM_OP_RELEASE) {
                if (write_torque(a, 0) != STSB_OK) return; /* retry next tick */
                a->torque_on = 0;
                a->state = ARM_ST_PARKED;
                finish(a, ARM_DONE_COMPLETED, 0, 1, err, 0, 0);
                a->state = ARM_ST_PARKED;
            } else {
                finish(a, ARM_DONE_COMPLETED, 0, 1, err, 0, 0);
            }
        } else if ((uint32_t)(now - a->op_t0) > kSettleTimeoutMs) {
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TIMEOUT, 1, 0, 0, 0);
        }
    }
}

/* ---- Enable sequence --------------------------------------------------------------- */
/* A failed enable never cuts a rail that was already on: the servos may be holding the arm and
 * the arm falls when the rail drops (it cannot be parked when a servo does not answer). It
 * returns to the state it came from (parked, or the latched fault); only an enable that
 * switched the rail on itself switches it off again. */
static void enable_abort(arm *a, uint8_t fault) {
    arm_state back = a->enable_from == ARM_ST_PARKED ? ARM_ST_PARKED : ARM_ST_FAULT;
    a->fault_code = fault;
    if (a->enable_rail_on) {
        if (fault == ARM_FAULT_LIMIT) a->limit_latched = 1; /* recoverable by a move back inside */
        a->state = back;
    } else {
        power_request_disable(&a->pwr);
        a->hw->servo_en(a->hw->ctx, 0);
        a->rail_applied = 0;
        if (a->tool_state != TOOL_ST_NONE) tool_off(a);
        a->state = ARM_ST_DISABLED;
    }
    finish(a, ARM_DONE_FAILED, fault, 0, 0, 0, 0);
    a->state = a->enable_rail_on ? back : ARM_ST_DISABLED;
}

static void enable_step(arm *a, uint32_t now) {
    unsigned j;
    switch (a->op_step) {
    case 0: /* wait for the self-test and ramp */
        if (a->pwr.state == PWR_ON && a->ina_ok) {
            a->op_step = 1;
            a->op_t0 = now;
        } else if ((uint32_t)(now - a->op_t1) > 2000u) {
            enable_abort(a, ARM_FAULT_SELFTEST);
        }
        break;
    case 1: /* servos reboot when the rail returns */
        if ((uint32_t)(now - a->op_t0) >= kServoBootMs) {
            a->op_step = 2;
            a->op_aux = 0;
            a->cfg_retry = 0;
            a->op_t0 = now;
        }
        break;
    case 2: { /* ping every arm servo */
        int rc = sts_bus_ping(&a->bus, servo_id(a->op_aux), 0);
        bus_note(a, rc);
        if (rc == STSB_OK) {
            a->cfg_retry = 0;
            if (++a->op_aux >= ARM_NUM_JOINTS) {
                a->op_step = a->op == ARM_OP_CALIBRATE ? 20u : 3u;
                a->op_aux = 0;
                cfg_reset(a);
            }
        } else if (++a->cfg_retry >= 10u) {
            enable_abort(a, ARM_FAULT_SERVO_COMM);
        }
        break;
    }
    case 3: { /* program and verify EEPROM limits and torque caps */
        int rc = cfg_run(a, a->op_aux);
        if (rc < 0) {
            enable_abort(a, a->bus.timeouts != 0 && a->cfg_retry >= 3u ? ARM_FAULT_SERVO_COMM
                                                                       : ARM_FAULT_CONFIG);
        } else if (rc == 1 && ++a->op_aux >= ARM_NUM_JOINTS) {
            a->op_step = 4;
            a->op_aux = 0;
            a->cfg_retry = 0;
            a->op_t0 = now;
        }
        break;
    }
    case 4: { /* measure the pose and apply the limits with a margin before torque-on */
        if (telemetry_read(a, a->op_aux, now) != STSB_OK) {
            if (++a->cfg_retry >= 5u) enable_abort(a, ARM_FAULT_SERVO_COMM);
            break;
        }
        a->cfg_retry = 0;
        if (++a->op_aux < ARM_NUM_JOINTS) break;
        for (j = 0; j < ARM_NUM_JOINTS; ++j) a->q_cmd.q[j] = a->sv[j].pos_deg;
        a->move_limit = arm_check_pose(&a->q_cmd, ARM_ENABLE_MARGIN_DEG);
        if (a->move_limit != ARM_LIMIT_NONE) {
            enable_abort(a, ARM_FAULT_LIMIT);
        } else {
            a->op_step = 5;
        }
        break;
    }
    case 5: /* goal = present position for every servo, then torque on */
        a->servo_speed_steps = 600u;
        if (write_arm_goals(a, &a->q_cmd) != STSB_OK) {
            if (++a->cfg_retry >= 3u) enable_abort(a, ARM_FAULT_BUS);
            break;
        }
        a->op_step = 6;
        break;
    case 6:
        if (write_torque(a, 1) != STSB_OK) {
            if (++a->cfg_retry >= 3u) enable_abort(a, ARM_FAULT_BUS);
            break;
        }
        a->torque_on = 1;
        a->pose_unknown = 0;
        a->limit_latched = 0;
        a->fault_code = ARM_FAULT_NONE;
        a->state = ARM_ST_READY;
        for (j = 0; j < ARM_NUM_JOINTS; ++j) a->sv[j].valid = 0;
        finish(a, ARM_DONE_COMPLETED, 0, 1, 0, 0, 0);
        break;
    case 20: { /* calibrate: read every joint's raw position (torque stays off, nothing moves) */
        if (telemetry_read(a, a->op_aux, now) != STSB_OK) {
            if (++a->cfg_retry >= 5u) enable_abort(a, ARM_FAULT_SERVO_COMM);
            break;
        }
        a->cfg_retry = 0;
        if (++a->op_aux < ARM_NUM_JOINTS) break;
        /* The arm rests at the rest pose: that raw position defines each joint's zero. */
        a->cal_new = a->cal;
        for (j = 0; j < ARM_NUM_JOINTS; ++j) {
            const arm_servo_spec *sp = &kArmServos[j];
            float rest_raw = (float)a->cal_new.sign[j] * kArmRestPose[j] * sp->ratio * ARM_SERVO_COUNTS / 360.0f;
            a->cal_new.raw_zero[j] = (int16_t)(a->sv[j].raw_steps - (int32_t)lroundf(rest_raw));
        }
        /* Refuse a zero that would put a joint range across the encoder wrap (with 20 counts spare). */
        for (j = 0; j < ARM_NUM_JOINTS; ++j) {
            int32_t lo, hi;
            if (arm_to_raw(&a->cal_new, j, kArmServos[j].lo_deg, &lo) != 0 ||
                arm_to_raw(&a->cal_new, j, kArmServos[j].hi_deg, &hi) != 0 || lo < 20 || hi > 4075) {
                enable_abort(a, ARM_FAULT_CALIBRATION);
                return;
            }
        }
        a->op_step = 21;
        break;
    }
    case 21: /* flash writes mask interrupts: save only with the rail off (E-stop IRQ not needed) */
        power_request_disable(&a->pwr);
        a->hw->servo_en(a->hw->ctx, 0);
        a->rail_applied = 0;
        a->op_t0 = now;
        a->op_step = 22;
        break;
    case 22:
        if (a->ina_ok && a->rail_mv < PWR_RAIL_DEAD_MV && (uint32_t)(now - a->op_t0) >= 60u) {
            a->op_step = 23;
        } else if ((uint32_t)(now - a->op_t0) > 1000u) {
            enable_abort(a, ARM_FAULT_CALIBRATION);
        }
        break;
    case 23:
        if (a->hw->cal_save == 0 || a->hw->cal_save(a->hw->ctx, &a->cal_new) != 0) {
            enable_abort(a, ARM_FAULT_CALIBRATION);
            break;
        }
        a->cal = a->cal_new;
        a->calibrated = 1;
        a->fault_code = ARM_FAULT_NONE;
        a->state = ARM_ST_DISABLED;
        for (j = 0; j < ARM_NUM_SERVOS; ++j) a->sv[j].valid = 0;
        finish(a, ARM_DONE_COMPLETED, 0, 1, 0, 0, 0);
        a->state = ARM_ST_DISABLED;
        break;
    default:
        break;
    }
}

/* ---- Tool procedures (INTERFACE.md section 5) ------------------------------------ */
static void tool_mount_step(arm *a, uint32_t now) {
    unsigned s = tool_servo_index(a->tool_id);
    switch (a->op_step) {
    case 0: /* TOOL_EN was raised by the command; wait 50 ms */
        if ((uint32_t)(now - a->tool_t0) >= kToolPowerMs) {
            if (s >= ARM_NUM_SERVOS) { /* passive tool: nothing to ping */
                a->tool_state = TOOL_ST_READY;
                finish(a, ARM_DONE_COMPLETED, 0, 1, (float)a->tool_id, 0, 0);
            } else {
                a->op_step = 1;
                a->cfg_retry = 0;
            }
        }
        break;
    case 1: {
        int rc = sts_bus_ping(&a->bus, servo_id(s), 0);
        bus_note(a, rc);
        if (rc == STSB_OK) {
            a->op_step = 2;
            cfg_reset(a);
        } else if (++a->cfg_retry >= 10u) {
            tool_off(a);
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL, 1, 0, 0, 0);
        }
        break;
    }
    case 2: {
        int rc = cfg_run(a, s);
        if (rc < 0) {
            tool_off(a);
            finish(a, ARM_DONE_FAILED, ARM_FAULT_CONFIG, 1, 0, 0, 0);
        } else if (rc == 1) {
            a->op_step = 3;
            a->cfg_retry = 0;
        }
        break;
    }
    case 3: { /* goal = present, torque on; the knob's present multi-turn position is zero */
        if (telemetry_read(a, s, now) != STSB_OK) {
            if (++a->cfg_retry >= 5u) {
                tool_off(a);
                finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL, 1, 0, 0, 0);
            }
            break;
        }
        if (s == ARM_S_KNOB) {
            a->knob_zero_steps = a->sv[s].raw_steps;
            a->sv[s].pos_deg = 0.0f;
        }
        if (write_tool_goal(a, s, a->sv[s].raw_steps, 300u) != STSB_OK ||
            write_tool_torque_enable(a, s, 1) != STSB_OK) {
            if (++a->cfg_retry >= 5u) {
                tool_off(a);
                finish(a, ARM_DONE_FAILED, ARM_FAULT_TOOL, 1, 0, 0, 0);
            }
            break;
        }
        if (a->tool_id == ARM_TOOL_BUTTON_PRESSER)
            a->fsr_base = a->hw->adc_read(a->hw->ctx, ARM_ADC_TOOL_AUX1);
        a->tool_state = TOOL_ST_READY;
        a->sv[s].valid = 0;
        finish(a, ARM_DONE_COMPLETED, 0, 1, (float)a->tool_id, 0, 0);
        break;
    }
    default:
        break;
    }
}

static void tool_unmount_step(arm *a, uint32_t now) {
    unsigned s = tool_servo_index(a->tool_id);
    switch (a->op_step) {
    case 0: /* disable torque on the tool servo (best effort: it may already be gone) */
        if (s < ARM_NUM_SERVOS) (void)write_tool_torque_enable(a, s, 0);
        a->hw->tool_en(a->hw->ctx, 0);
        a->tool_state = TOOL_ST_UNMOUNTING;
        a->tool_t0 = now;
        a->op_step = 1;
        break;
    case 1: /* no ADC on V_TOOL: wait out the discharge before the unlocking roll */
        if ((uint32_t)(now - a->tool_t0) >= kToolDischargeMs) {
            a->tool_state = a->tool_id >= 1u && a->tool_id <= 4u ? TOOL_ST_DETECTED : TOOL_ST_NONE;
            finish(a, ARM_DONE_COMPLETED, 0, 1, 0, 0, 0);
        }
        break;
    default:
        break;
    }
}

/* Stall detection shared by the tool motions: the servo stopped short of its goal. */
static int stalled(arm *a, const arm_servo_state *v, float err, float tol, uint32_t now) {
    if (v->moving || err <= tol) {
        a->stall_active = 0;
        return 0;
    }
    if (!a->stall_active) {
        a->stall_active = 1;
        a->stall_t0 = now;
    }
    return (uint32_t)(now - a->stall_t0) >= kStallMs;
}

static void grip_step(arm *a, uint32_t now) {
    unsigned s = ARM_S_GRIPPER;
    const arm_servo_state *v = &a->sv[s];
    int32_t raw;
    switch (a->op_step) {
    case 0:
        if (write_tool_torque_limit(a, s, (uint16_t)(a->tool_limit * 10u)) != STSB_OK) break;
        a->op_step = 1;
        break;
    case 1: {
        float servo_deg = a->tool_target * 0.5f / ARM_GRIPPER_PINION_R_MM * kRadToDeg;
        if (arm_to_raw(&a->cal, s, servo_deg, &raw) != 0 ||
            write_tool_goal(a, s, raw, 1500u) != STSB_OK) {
            if (++a->cfg_retry >= 3u) finish(a, ARM_DONE_FAILED, ARM_FAULT_BUS, 0, 0, 0, 0);
            break;
        }
        a->op_t0 = now;
        a->op_step = 2;
        break;
    }
    case 2: {
        float width, err;
        if (!v->valid || before(v->stamp_ms, a->op_t0)) break;
        width = 2.0f * ARM_GRIPPER_PINION_R_MM * v->pos_deg * kDegToRad;
        err = fabsf(width - a->tool_target);
        if (!v->moving && err <= 1.0f) {
            finish(a, ARM_DONE_COMPLETED, 0, 1, width, 0.0f, 0);
        } else if (stalled(a, v, err, 1.0f, now)) {
            finish(a, ARM_DONE_COMPLETED, 0, 1, width, 1.0f, 0); /* stopped on an object */
        } else if ((uint32_t)(now - a->op_t0) > kToolOpTimeoutMs) {
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TIMEOUT, 1, width, 0, 0);
        }
        break;
    }
    default:
        break;
    }
}

static void turn_step(arm *a, uint32_t now) {
    unsigned s = ARM_S_KNOB;
    const arm_servo_state *v = &a->sv[s];
    switch (a->op_step) {
    case 0:
        if (write_tool_torque_limit(a, s, a->tool_limit) != STSB_OK) break;
        a->op_step = 1;
        break;
    case 1: {
        int32_t steps = a->knob_zero_steps +
                        (int32_t)lroundf(a->tool_target * ARM_KNOB_RATIO * ARM_SERVO_COUNTS / 360.0f);
        if (write_tool_goal(a, s, steps, 800u) != STSB_OK) {
            if (++a->cfg_retry >= 3u) finish(a, ARM_DONE_FAILED, ARM_FAULT_BUS, 0, 0, 0, 0);
            break;
        }
        a->op_t0 = now;
        a->op_step = 2;
        break;
    }
    case 2: {
        float err;
        if (!v->valid || before(v->stamp_ms, a->op_t0)) break;
        err = fabsf(v->pos_deg - a->tool_target);
        if (!v->moving && err <= 2.0f) finish(a, ARM_DONE_COMPLETED, 0, 1, v->pos_deg, 1.0f, 0);
        else if (stalled(a, v, err, 2.0f, now)) /* the torque cap / a stop held it short: a failure,
                                                  * the angle reached stays readable as knob_angle_deg */
            finish(a, ARM_DONE_FAILED, ARM_FAULT_STALL, 1, v->pos_deg, 0.0f, 0);
        else if ((uint32_t)(now - a->op_t0) > 30000u)
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TIMEOUT, 1, v->pos_deg, 0, 0);
        break;
    }
    default:
        break;
    }
}

static float fsr_pct(const arm *a) {
    uint16_t now_code = a->hw->adc_read(a->hw->ctx, ARM_ADC_TOOL_AUX1);
    float span = 4095.0f - (float)a->fsr_base;
    float f = span > 1.0f ? ((float)now_code - (float)a->fsr_base) * 100.0f / span : 0.0f;
    return f < 0.0f ? 0.0f : (f > 100.0f ? 100.0f : f);
}

static float presser_depth_mm(float servo_deg) {
    return ARM_PRESSER_THROW_MM * (1.0f - cosf(servo_deg * kDegToRad));
}

static void press_step(arm *a, uint32_t now) {
    unsigned s = ARM_S_PRESSER;
    const arm_servo_state *v = &a->sv[s];
    int32_t raw;
    switch (a->op_step) {
    case 0:
        if (write_tool_torque_limit(a, s, kArmServos[s].torque_permille) != STSB_OK) break;
        a->tool_peak = 0.0f;
        a->op_step = 1;
        break;
    case 1: { /* extend toward the commanded depth */
        float deg = acosf(1.0f - a->tool_target / ARM_PRESSER_THROW_MM) * kRadToDeg;
        if (arm_to_raw(&a->cal, s, deg, &raw) != 0 || write_tool_goal(a, s, raw, 400u) != STSB_OK) {
            if (++a->cfg_retry >= 3u) finish(a, ARM_DONE_FAILED, ARM_FAULT_BUS, 0, 0, 0, 0);
            break;
        }
        a->op_t0 = now;
        a->op_step = 2;
        break;
    }
    case 2: { /* watch the FSR: stop at the force limit, or at the depth */
        float f = fsr_pct(a);
        if (f > a->tool_peak) a->tool_peak = f;
        if (v->valid && !before(v->stamp_ms, a->op_t0) &&
            (f >= (float)a->tool_limit || (!v->moving && fabsf(presser_depth_mm(v->pos_deg) - a->tool_target) < 0.3f))) {
            a->tool_target = presser_depth_mm(v->pos_deg); /* depth actually reached */
            if (arm_to_raw(&a->cal, s, 0.0f, &raw) != 0 || write_tool_goal(a, s, raw, 800u) != STSB_OK)
                break; /* retry next tick */
            a->op_t0 = now;
            a->op_step = 3;
        } else if ((uint32_t)(now - a->op_t0) > kToolOpTimeoutMs) {
            /* Did not reach the depth or the force in time: pull the tip back before failing. */
            a->op_aux = 1;
            if (arm_to_raw(&a->cal, s, 0.0f, &raw) == 0) (void)write_tool_goal(a, s, raw, 800u);
            a->op_t0 = now;
            a->op_step = 3;
        }
        break;
    }
    case 3: /* retract to the closed stop */
        if (v->valid && !before(v->stamp_ms, a->op_t0 + 100u) && !v->moving && v->pos_deg < 3.0f)
            finish(a, a->op_aux ? ARM_DONE_FAILED : ARM_DONE_COMPLETED, a->op_aux ? ARM_FAULT_TIMEOUT : 0,
                   1, a->tool_peak, a->tool_target, 0);
        else if ((uint32_t)(now - a->op_t0) > kToolOpTimeoutMs)
            finish(a, ARM_DONE_FAILED, ARM_FAULT_TIMEOUT, 1, a->tool_peak, a->tool_target, 0);
        break;
    default:
        break;
    }
}

/* ---- Freeze after an abort of a tool motion ------------------------------------------ */
static void freeze_step(arm *a, uint32_t now) {
    unsigned s;
    if (a->freeze_servo == 0 || !arm_servos_powered(a)) {
        a->freeze_servo = 0;
        return;
    }
    s = (unsigned)a->freeze_servo - 1u;
    if (telemetry_read(a, s, now) != STSB_OK) return;
    if (write_tool_goal(a, s, a->sv[s].raw_steps, 300u) == STSB_OK) a->freeze_servo = 0;
}

/* ---- Main tick ----------------------------------------------------------------------- */
static void idle_state(arm *a) {
    if (a->op != ARM_OP_NONE) return;
    if (a->state == ARM_ST_BOOT || a->state == ARM_ST_NO_POWER || a->state == ARM_ST_DISABLED) {
        if (a->pwr.latched) return;
        a->state = a->vin_mv < PWR_VIN_MIN_MV ? ARM_ST_NO_POWER : ARM_ST_DISABLED;
    }
}

static void stop_check(arm *a, uint32_t now) {
    unsigned s;
    int safe = 0;
    if (!a->stop_pending) return;
    if (a->ina_ok && a->rail_mv < PWR_RAIL_DEAD_MV && !a->pwr.rail_cmd) {
        safe = 1; /* no power: nothing can move (measured from the rail) */
    } else if (arm_servos_powered(a) && a->op == ARM_OP_NONE && !a->freeze_servo) {
        safe = 1;
        for (s = 0; s < ARM_NUM_SERVOS && safe; ++s) {
            if (!scan_eligible(a, s)) continue;
            if (!a->sv[s].valid || before(a->sv[s].stamp_ms, a->stop_t0) || a->sv[s].moving) safe = 0;
        }
    }
    if (safe) {
        a->stop_pending = 0;
        if (a->sink != 0 && a->sink->stop_confirmed != 0) a->sink->stop_confirmed(a->sink->ctx, 1);
    }
    (void)now;
}

static void led_update(arm *a) {
    uint8_t c;
    switch (a->state) {
    case ARM_ST_ESTOP: c = 1; break;           /* red solid */
    case ARM_ST_FAULT: c = 2; break;           /* red blinking: handled by the port via code 2 */
    case ARM_ST_READY:
    case ARM_ST_MOVING: c = 3; break;          /* green */
    case ARM_ST_NO_POWER: c = 4; break;        /* blue blinking */
    default: c = 5; break;                     /* blue */
    }
    if (c == a->led_last) return;
    a->led_last = c;
    switch (c) {
    case 1: case 2: a->hw->led(a->hw->ctx, 1, 0, 0); break;
    case 3: a->hw->led(a->hw->ctx, 0, 1, 0); break;
    default: a->hw->led(a->hw->ctx, 0, 0, 1); break;
    }
}

void arm_tick(arm *a) {
    uint32_t now = a->hw->millis(a->hw->ctx);
    power_step(a, now, 0);
    react_power(a, now);
    tool_step(a, now);
    idle_state(a);
    switch (a->op) {
    case ARM_OP_ENABLE:
    case ARM_OP_CALIBRATE: enable_step(a, now); break;
    case ARM_OP_MOVE:
    case ARM_OP_HOME:
    case ARM_OP_RELEASE: move_step(a, now); break;
    case ARM_OP_TOOL_MOUNT: tool_mount_step(a, now); break;
    case ARM_OP_TOOL_UNMOUNT: tool_unmount_step(a, now); break;
    case ARM_OP_GRIP: grip_step(a, now); break;
    case ARM_OP_TURN: turn_step(a, now); break;
    case ARM_OP_PRESS: press_step(a, now); break;
    default: break;
    }
    freeze_step(a, now);
    scan_step(a, now);
    stop_check(a, now);
    led_update(a);
}

/* ---- Commands ------------------------------------------------------------------------ */
static unsigned hottest_joint_c(const arm *a) {
    unsigned j, hot = 0;
    for (j = 0; j < ARM_NUM_JOINTS; ++j)
        if (a->sv[j].valid && a->sv[j].temp_c > hot) hot = a->sv[j].temp_c;
    return hot;
}

/* allow_recover: a latched limit/following/servo fault still lets a move back inside run. */
static arm_refusal gate_motion_ex(const arm *a, uint8_t *detail, int allow_recover) {
    *detail = ARM_WHY_NONE;
    switch (a->state) {
    case ARM_ST_READY: break;
    case ARM_ST_MOVING: return ARM_REFUSE_BUSY;
    case ARM_ST_ESTOP: *detail = a->pwr.latched && a->sense ? ARM_WHY_ESTOP_PRESSED : ARM_WHY_ESTOP_LATCHED; return ARM_REFUSE_INHIBITED;
    case ARM_ST_FAULT:
        if (allow_recover && a->limit_latched && !a->pwr.hard_fault && a->torque_on &&
            arm_servos_powered(a))
            break;
        *detail = a->pwr.hard_fault ? ARM_WHY_HARD_FAULT : ARM_WHY_FAULT;
        return ARM_REFUSE_INHIBITED;
    case ARM_ST_PARKED: *detail = ARM_WHY_PARKED; return ARM_REFUSE_PRECONDITION;
    case ARM_ST_NO_POWER: *detail = ARM_WHY_NO_POWER; return ARM_REFUSE_PRECONDITION;
    default: *detail = ARM_WHY_NOT_ENABLED; return ARM_REFUSE_PRECONDITION;
    }
    if (a->stop_pending) {
        *detail = ARM_WHY_STOPPING;
        return ARM_REFUSE_INHIBITED;
    }
    if (a->op != ARM_OP_NONE) return ARM_REFUSE_BUSY;
    if (hottest_joint_c(a) >= kTempFaultC) { /* the servo protects itself at 70 C: do not ask for more */
        *detail = ARM_WHY_OVERTEMP;
        return ARM_REFUSE_INHIBITED;
    }
    return ARM_OK;
}

static arm_refusal gate_motion(const arm *a, uint8_t *detail) { return gate_motion_ex(a, detail, 0); }

arm_refusal arm_cmd_enable(arm *a, uint8_t *detail) {
    uint32_t now = a->hw->millis(a->hw->ctx);
    power_in in;
    int r;
    *detail = ARM_WHY_NONE;
    if (a->op != ARM_OP_NONE) return ARM_REFUSE_BUSY;
    if (a->state == ARM_ST_READY) return ARM_OK; /* already enabled: nothing to do */
    if (a->stop_pending) {
        *detail = ARM_WHY_STOPPING;
        return ARM_REFUSE_INHIBITED;
    }
    if (!a->calibrated) { /* limits are relative to the joint zero: calibrate first */
        *detail = ARM_WHY_NOT_CALIBRATED;
        return ARM_REFUSE_PRECONDITION;
    }
    power_step(a, now, 1); /* fresh sense, edge, rail and VIN; applies any E-stop first */
    react_power(a, now);
    a->enable_rail_on = (a->pwr.state == PWR_ON && a->ina_ok && a->rail_mv >= PWR_RAIL_OK_MV) ? 1u : 0u;
    in.now_ms = now;
    in.sense = a->sense;
    in.edge = 0;
    in.ina_ok = a->ina_ok;
    in.rail_mv = a->rail_mv;
    in.rail_ma = a->rail_ma;
    in.vin_mv = a->vin_mv;
    r = power_request_enable(&a->pwr, &in);
    switch (r) {
    case PWR_ENABLE_OK: break;
    case PWR_REFUSE_ESTOP: *detail = ARM_WHY_ESTOP_PRESSED; return ARM_REFUSE_INHIBITED;
    case PWR_REFUSE_HARD_FAULT: *detail = ARM_WHY_HARD_FAULT; return ARM_REFUSE_INHIBITED;
    case PWR_REFUSE_NO_POWER: *detail = ARM_WHY_NO_POWER; return ARM_REFUSE_PRECONDITION;
    case PWR_REFUSE_BUSY: return ARM_REFUSE_BUSY;
    default: *detail = ARM_WHY_SENSE; return ARM_REFUSE_PRECONDITION;
    }
    a->enable_from = a->state;
    if (a->tool_state == TOOL_ST_LOST || a->tool_state == TOOL_ST_UNMOUNTING) tool_off(a);
    a->op = ARM_OP_ENABLE;
    a->op_step = 0;
    a->op_t1 = now;
    a->state = ARM_ST_ENABLING;
    a->hw->servo_en(a->hw->ctx, a->pwr.rail_cmd);
    a->rail_applied = a->pwr.rail_cmd;
    return ARM_OK;
}

static arm_refusal check_goal(const float q[ARM_NUM_JOINTS], uint8_t *detail) {
    arm_pose p;
    uint8_t lim;
    memcpy(p.q, q, sizeof p.q);
    lim = arm_check_pose(&p, 0.0f);
    if (lim != ARM_LIMIT_NONE) {
        *detail = lim;
        return ARM_REFUSE_RANGE;
    }
    return ARM_OK;
}

/* Calibration: with the arm resting at the rest pose on its support and the rail off, power the
 * rail with torque off, read every joint's raw position, define it as the rest pose, cut the rail
 * and persist the zero offsets. Nothing moves; the arm needs an explicit enable afterwards. */
arm_refusal arm_cmd_calibrate(arm *a, uint8_t *detail) {
    uint32_t now = a->hw->millis(a->hw->ctx);
    power_in in;
    int r;
    *detail = ARM_WHY_NONE;
    if (a->op != ARM_OP_NONE) return ARM_REFUSE_BUSY;
    if (a->state != ARM_ST_DISABLED && a->state != ARM_ST_NO_POWER && a->state != ARM_ST_ESTOP) {
        *detail = ARM_WHY_NOT_DISABLED;
        return ARM_REFUSE_PRECONDITION;
    }
    power_step(a, now, 1);
    react_power(a, now);
    in.now_ms = now;
    in.sense = a->sense;
    in.edge = 0;
    in.ina_ok = a->ina_ok;
    in.rail_mv = a->rail_mv;
    in.rail_ma = a->rail_ma;
    in.vin_mv = a->vin_mv;
    r = power_request_enable(&a->pwr, &in);
    switch (r) {
    case PWR_ENABLE_OK: break;
    case PWR_REFUSE_ESTOP: *detail = ARM_WHY_ESTOP_PRESSED; return ARM_REFUSE_INHIBITED;
    case PWR_REFUSE_HARD_FAULT: *detail = ARM_WHY_HARD_FAULT; return ARM_REFUSE_INHIBITED;
    case PWR_REFUSE_NO_POWER: *detail = ARM_WHY_NO_POWER; return ARM_REFUSE_PRECONDITION;
    case PWR_REFUSE_BUSY: return ARM_REFUSE_BUSY;
    default: *detail = ARM_WHY_SENSE; return ARM_REFUSE_PRECONDITION;
    }
    a->enable_rail_on = 0;
    a->enable_from = a->state;
    a->op = ARM_OP_CALIBRATE;
    a->op_step = 0;
    a->op_t1 = now;
    a->state = ARM_ST_ENABLING;
    a->hw->servo_en(a->hw->ctx, a->pwr.rail_cmd);
    a->rail_applied = a->pwr.rail_cmd;
    return ARM_OK;
}

arm_refusal arm_cmd_move(arm *a, const float q[ARM_NUM_JOINTS], uint8_t speed_pct, uint8_t *detail) {
    arm_pose goal;
    arm_refusal r;
    *detail = ARM_WHY_NONE;
    /* Device limits first: they do not depend on the arm's state, and the refusal must
     * name the limit (joint index, or 0x10 + coupled limit). */
    r = check_goal(q, detail);
    if (r != ARM_OK) return r;
    if (speed_pct < 5u || speed_pct > 100u) {
        *detail = 0xF0u;
        return ARM_REFUSE_RANGE;
    }
    r = gate_motion_ex(a, detail, 1);
    if (r != ARM_OK) return r;
    memcpy(goal.q, q, sizeof goal.q);
    traj_start(a, &goal, speed_pct, ARM_OP_MOVE, a->hw->millis(a->hw->ctx));
    return ARM_OK;
}

arm_refusal arm_cmd_home(arm *a, uint8_t speed_pct, uint8_t *detail) {
    arm_pose goal;
    arm_refusal r = gate_motion_ex(a, detail, 1);
    if (r != ARM_OK) return r;
    if (speed_pct < 5u || speed_pct > 100u) {
        *detail = 0xF0u;
        return ARM_REFUSE_RANGE;
    }
    memcpy(goal.q, kArmRestPose, sizeof goal.q);
    traj_start(a, &goal, speed_pct > kHomeSpeedCapPct ? kHomeSpeedCapPct : speed_pct, ARM_OP_HOME,
               a->hw->millis(a->hw->ctx));
    return ARM_OK;
}

arm_refusal arm_cmd_hold(arm *a, uint8_t *detail) {
    *detail = ARM_WHY_NONE;
    if (a->state == ARM_ST_MOVING || (a->state == ARM_ST_READY && a->op != ARM_OP_NONE)) {
        (void)arm_cancel(a, 1);
        return ARM_OK;
    }
    if (a->state == ARM_ST_READY) return ARM_OK;
    return gate_motion(a, detail) == ARM_OK ? ARM_OK : ARM_REFUSE_PRECONDITION;
}

arm_refusal arm_cmd_release(arm *a, uint8_t *detail) {
    arm_pose goal;
    arm_refusal r = gate_motion(a, detail);
    if (r != ARM_OK) return r;
    /* The arm falls when torque goes away: park it at the rest pose first, slowly. */
    memcpy(goal.q, kArmRestPose, sizeof goal.q);
    traj_start(a, &goal, 25u, ARM_OP_RELEASE, a->hw->millis(a->hw->ctx));
    return ARM_OK;
}

static arm_refusal gate_tool(const arm *a, uint8_t want_tool, uint8_t *detail) {
    arm_refusal r = gate_motion(a, detail);
    if (r != ARM_OK) return r;
    if (a->tool_state != TOOL_ST_READY) {
        *detail = a->tool_id == ARM_TOOL_NONE ? ARM_WHY_NO_TOOL : ARM_WHY_TOOL_NOT_READY;
        return ARM_REFUSE_PRECONDITION;
    }
    if (a->tool_id != want_tool) {
        *detail = ARM_WHY_WRONG_TOOL;
        return ARM_REFUSE_PRECONDITION;
    }
    return ARM_OK;
}

arm_refusal arm_cmd_tool_mount(arm *a, uint8_t *detail) {
    arm_refusal r = gate_motion(a, detail);
    if (r != ARM_OK) return r;
    if (a->tool_id == ARM_TOOL_NONE) {
        *detail = ARM_WHY_NO_TOOL;
        return ARM_REFUSE_PRECONDITION;
    }
    if (a->tool_id < 1u || a->tool_id > 4u) {
        *detail = ARM_WHY_TOOL_RESERVED;
        return ARM_REFUSE_PRECONDITION;
    }
    if (a->tool_state != TOOL_ST_DETECTED) {
        *detail = a->tool_state == TOOL_ST_READY ? ARM_WHY_TOOL_MOUNTED : ARM_WHY_TOOL_NOT_READY;
        return ARM_REFUSE_PRECONDITION;
    }
    a->hw->tool_en(a->hw->ctx, 1);
    a->tool_state = TOOL_ST_POWERING;
    a->tool_t0 = a->hw->millis(a->hw->ctx);
    a->op = ARM_OP_TOOL_MOUNT;
    a->op_step = 0;
    a->cfg_retry = 0;
    return ARM_OK;
}

arm_refusal arm_cmd_tool_unmount(arm *a, uint8_t *detail) {
    arm_refusal r = gate_motion(a, detail);
    if (r != ARM_OK) return r;
    if (a->tool_state != TOOL_ST_READY) {
        *detail = ARM_WHY_TOOL_NOT_READY;
        return ARM_REFUSE_PRECONDITION;
    }
    a->op = ARM_OP_TOOL_UNMOUNT;
    a->op_step = 0;
    return ARM_OK;
}

arm_refusal arm_cmd_grip(arm *a, float width_mm, uint8_t force_pct, uint8_t *detail) {
    arm_refusal r;
    if (!(width_mm >= 0.0f && width_mm <= 2.0f * ARM_GRIPPER_STROKE_MM) || force_pct < 1u ||
        force_pct > kArmServos[ARM_S_GRIPPER].torque_permille / 10u) {
        *detail = force_pct < 1u || force_pct > 15u ? 1u : 0u; /* argument index */
        return ARM_REFUSE_RANGE;
    }
    r = gate_tool(a, ARM_TOOL_GRIPPER, detail);
    if (r != ARM_OK) return r;
    a->tool_target = width_mm;
    a->tool_limit = force_pct;
    a->op = ARM_OP_GRIP;
    a->op_step = 0;
    a->cfg_retry = 0;
    a->stall_active = 0;
    return ARM_OK;
}

arm_refusal arm_cmd_turn(arm *a, float angle_deg, uint8_t torque_permille, uint8_t *detail) {
    arm_refusal r;
    if (!(fabsf(angle_deg) <= ARM_KNOB_MAX_DEG) || torque_permille < 1u ||
        torque_permille > kArmServos[ARM_S_KNOB].torque_permille) {
        *detail = torque_permille < 1u || torque_permille > kArmServos[ARM_S_KNOB].torque_permille ? 1u : 0u;
        return ARM_REFUSE_RANGE;
    }
    r = gate_tool(a, ARM_TOOL_KNOB_TURNER, detail);
    if (r != ARM_OK) return r;
    a->tool_target = angle_deg;
    a->tool_limit = torque_permille;
    a->op = ARM_OP_TURN;
    a->op_step = 0;
    a->cfg_retry = 0;
    a->stall_active = 0;
    return ARM_OK;
}

arm_refusal arm_cmd_press(arm *a, float depth_mm, uint8_t force_limit_pct, uint8_t *detail) {
    arm_refusal r;
    if (!(depth_mm >= 0.0f && depth_mm <= ARM_PRESSER_STROKE_MM - 0.2f) || force_limit_pct < 1u ||
        force_limit_pct > 100u) {
        *detail = force_limit_pct < 1u || force_limit_pct > 100u ? 1u : 0u;
        return ARM_REFUSE_RANGE;
    }
    r = gate_tool(a, ARM_TOOL_BUTTON_PRESSER, detail);
    if (r != ARM_OK) return r;
    a->tool_target = depth_mm;
    a->tool_limit = force_limit_pct;
    a->op_aux = 0;
    a->op = ARM_OP_PRESS;
    a->op_step = 0;
    a->cfg_retry = 0;
    return ARM_OK;
}

int arm_cancel(arm *a, int report) {
    arm_op_kind k = a->op;
    if (k == ARM_OP_NONE) return 0;
    /* Aborting is always safe: motion freezes at the last commanded waypoint (the servos keep
     * holding it), tool motions freeze at the measured position, and a half-done enable or
     * tool mount returns to the powered-off state. */
    a->traj_active = 0;
    switch (k) {
    case ARM_OP_ENABLE:
    case ARM_OP_CALIBRATE:
        a->op = ARM_OP_NONE;
        a->state = a->enable_rail_on ? (a->enable_from == ARM_ST_PARKED ? ARM_ST_PARKED : ARM_ST_FAULT)
                                     : ARM_ST_DISABLED;
        if (!a->enable_rail_on) {
            power_request_disable(&a->pwr);
            a->hw->servo_en(a->hw->ctx, 0);
            a->rail_applied = 0;
        }
        break;
    case ARM_OP_TOOL_MOUNT:
    case ARM_OP_TOOL_UNMOUNT:
        a->hw->tool_en(a->hw->ctx, 0);
        a->tool_state = a->tool_id >= 1u && a->tool_id <= 4u ? TOOL_ST_DETECTED : TOOL_ST_NONE;
        a->op = ARM_OP_NONE;
        break;
    case ARM_OP_GRIP:
    case ARM_OP_TURN:
    case ARM_OP_PRESS:
        a->freeze_servo = (uint8_t)(1u + tool_servo_index(a->tool_id));
        a->op = ARM_OP_NONE;
        break;
    default:
        a->op = ARM_OP_NONE;
        break;
    }
    if (a->state == ARM_ST_MOVING) a->state = ARM_ST_READY;
    if (report && a->sink != 0 && a->sink->finished != 0) {
        arm_completion d;
        memset(&d, 0, sizeof d);
        d.kind = k;
        d.status = ARM_DONE_CANCELED;
        d.fault = ARM_FAULT_STOPPED;
        a->sink->finished(a->sink->ctx, &d);
    }
    a->op_step = 0;
    return 1;
}

arm_stop_result arm_stop(arm *a, uint8_t *measured) {
    uint32_t now = a->hw->millis(a->hw->ctx);
    (void)arm_cancel(a, 0);
    /* An E-stop edge may be pending: apply it now so the latch exists before we answer. */
    power_step(a, now, 1);
    react_power(a, now);
    *measured = 0;
    if (a->ina_ok && a->rail_mv < PWR_RAIL_DEAD_MV && !a->pwr.rail_cmd) {
        *measured = 1; /* rail measured dead: nothing can move */
        a->stop_pending = 0;
        return ARM_STOP_CONFIRMED;
    }
    a->stop_pending = 1;
    a->stop_t0 = now;
    return ARM_STOP_INITIATED;
}

/* ---- Read side ------------------------------------------------------------------------ */
uint32_t arm_age_ms(const arm *a, const arm_servo_state *s) {
    return (uint32_t)(a->hw->millis(a->hw->ctx) - s->stamp_ms);
}

uint8_t arm_estop_state(const arm *a) { return a->pwr.estop; }

uint8_t arm_temperature_warning(const arm *a) { return hottest_joint_c(a) >= kTempWarnC ? 1u : 0u; }

uint8_t arm_tool_present(const arm *a) { return a->tool_id; }

float arm_gripper_opening_mm(const arm *a, uint8_t *valid) {
    const arm_servo_state *v = &a->sv[ARM_S_GRIPPER];
    *valid = v->valid && a->tool_id == ARM_TOOL_GRIPPER && a->tool_state == TOOL_ST_READY;
    return 2.0f * ARM_GRIPPER_PINION_R_MM * v->pos_deg * kDegToRad;
}

float arm_fsr_force_pct(const arm *a, uint8_t *valid) {
    *valid = a->tool_id == ARM_TOOL_BUTTON_PRESSER && a->tool_state == TOOL_ST_READY;
    return *valid ? fsr_pct(a) : 0.0f;
}

float arm_knob_sensor_deg(const arm *a) {
    /* AS5600 analog OUT: 0..3.3 V for 0..360 degrees, ratiometric to the controller 3V3. */
    return (float)a->hw->adc_read(a->hw->ctx, ARM_ADC_TOOL_AUX1) * 360.0f / 4095.0f;
}
