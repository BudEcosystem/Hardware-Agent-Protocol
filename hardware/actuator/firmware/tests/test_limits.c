/* Joint, coupled and speed limit enforcement (pure functions). */
#include <math.h>
#include <stdlib.h>

#include "arm_limits.h"
#include "arm_params.h"
#include "bhms_test.h"

static arm_pose pose(float a, float b, float c, float d, float e) {
    arm_pose p = {{a, b, c, d, e}};
    return p;
}

static void test_single_joint_ranges(void) {
    static const float lo[5] = {-150, -20, -5, -100, -150}, hi[5] = {150, 95, 125, 100, 150};
    unsigned j;
    for (j = 0; j < 5; ++j) {
        arm_pose p = pose(0, 30, 90, 45, 0);
        p.q[j] = lo[j];
        /* The extreme itself is allowed when no coupled limit is involved. */
        if (j == ARM_J_BASE_YAW || j == ARM_J_WRIST_ROLL) CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE);
        p.q[j] = lo[j] - 0.01f;
        CHECK(arm_check_pose(&p, 0.0f) == j);
        p.q[j] = hi[j] + 0.01f;
        CHECK(arm_check_pose(&p, 0.0f) == j);
    }
    {
        arm_pose p = pose(NAN, 0, 0, 0, 0);
        CHECK(arm_check_pose(&p, 0.0f) == ARM_J_BASE_YAW);
        p = pose(0, 0, 0, INFINITY, 0);
        CHECK(arm_check_pose(&p, 0.0f) == ARM_J_WRIST_PITCH);
    }
}

static void test_coupled_limits(void) {
    /* Each sum sits exactly on its limit (allowed) and just beyond it (refused, named). */
    arm_pose p = pose(0, 80, 95, 0, 0); /* forearm_pitch = 175 */
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE);
    p.q[ARM_J_ELBOW] = 95.01f;
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_COUPLED_BASE + 0);
    p = pose(0, 0, 100, 65, 0); /* hairpin = 165 */
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE);
    p.q[ARM_J_WRIST_PITCH] = 65.01f;
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_COUPLED_BASE + 1);
    p = pose(0, 20, 80, 83, 0); /* tool_pitch = 183, hairpin = 163, forearm = 100 */
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE);
    p.q[ARM_J_WRIST_PITCH] = 83.01f;
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_COUPLED_BASE + 2);
    /* The pose named in INTERFACE.md section 3.2: every joint inside its own range but the
     * gripper fingers end up inside the turret (shoulder 30, elbow 100, wrist +100). */
    p = pose(0, 30, 100, 100, 0);
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_COUPLED_BASE + 1); /* hairpin 200 > 165 */
    CHECK(strcmp(arm_limit_name(ARM_LIMIT_COUPLED_BASE + 1), "hairpin") == 0);
    CHECK(strcmp(arm_limit_name(0), "base_yaw") == 0 && strcmp(arm_limit_name(99), "unknown") == 0);
    /* The rest pose is valid, with margin. */
    p = pose(kArmRestPose[0], kArmRestPose[1], kArmRestPose[2], kArmRestPose[3], kArmRestPose[4]);
    CHECK(arm_check_pose(&p, ARM_ENABLE_MARGIN_DEG) == ARM_LIMIT_NONE);
    /* A margin tightens: a pose 1 deg inside the limit fails a 3 deg margin. */
    p = pose(0, 80, 94, 0, 0);
    CHECK(arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE);
    CHECK(arm_check_pose(&p, 3.0f) == ARM_LIMIT_COUPLED_BASE + 0);
}

/* Independent reference: the limits written out as plain inequalities. */
static int reference_ok(const arm_pose *p) {
    float s = p->q[1], e = p->q[2], w = p->q[3];
    return p->q[0] >= -150 && p->q[0] <= 150 && s >= -20 && s <= 95 && e >= -5 && e <= 125 &&
           w >= -100 && w <= 100 && p->q[4] >= -150 && p->q[4] <= 150 && s + e <= 175 &&
           e + w <= 165 && s + e + w <= 183;
}

static void test_random_agreement(void) {
    unsigned i, accepted = 0;
    srand(1234);
    for (i = 0; i < 200000; ++i) {
        arm_pose p;
        unsigned j;
        for (j = 0; j < 5; ++j) p.q[j] = (float)(rand() % 40001) / 100.0f - 200.0f; /* -200..200 */
        {
            int ref = reference_ok(&p);
            int got = arm_check_pose(&p, 0.0f) == ARM_LIMIT_NONE;
            CHECK(ref == got);
            accepted += (unsigned)ref;
        }
    }
    CHECK(accepted > 1000); /* the sample covers both sides */
}

static void test_step_recovery(void) {
    /* A waypoint may leave the allowed region only if it was already outside and moves back. */
    arm_pose inside = pose(0, 30, 90, 45, 0), out_a = pose(0, 30, 90, 90, 0) /* hairpin 180 */,
             out_b = pose(0, 30, 90, 80, 0) /* hairpin 170 */, out_c = pose(0, 30, 90, 95, 0);
    CHECK(arm_check_step(&inside, &inside) == ARM_LIMIT_NONE);
    CHECK(arm_check_step(&inside, &out_b) == ARM_LIMIT_COUPLED_BASE + 1); /* crossing out */
    CHECK(arm_check_step(&out_a, &out_b) == ARM_LIMIT_NONE);              /* recovering */
    CHECK(arm_check_step(&out_a, &inside) == ARM_LIMIT_NONE);
    CHECK(arm_check_step(&out_a, &out_c) != ARM_LIMIT_NONE);              /* getting worse */
    {
        arm_pose nan = pose(NAN, 0, 0, 0, 0);
        CHECK(arm_check_step(&inside, &nan) == ARM_J_BASE_YAW);
    }
    /* A joint outside its own range may only come back. */
    {
        arm_pose a = pose(155, 30, 90, 45, 0), b = pose(152, 30, 90, 45, 0), c = pose(158, 30, 90, 45, 0);
        CHECK(arm_check_step(&a, &b) == ARM_LIMIT_NONE);
        CHECK(arm_check_step(&a, &c) == ARM_J_BASE_YAW);
    }
}

static void test_speed_limits(void) {
    /* Servo no-load 4.7 rad/s divided by the ratio: yaw/wrist 269 deg/s, elbow half, shoulder a third. */
    CHECK(fabsf(arm_speed_limit_dps(ARM_J_BASE_YAW) - 269.3f) < 0.5f);
    CHECK(fabsf(arm_speed_limit_dps(ARM_J_ELBOW) - 134.6f) < 0.5f);
    CHECK(fabsf(arm_speed_limit_dps(ARM_J_SHOULDER) - 89.8f) < 0.5f);
    CHECK(kArmServos[ARM_J_SHOULDER].torque_permille == 780);
}

static void test_calibration(void) {
    arm_cal cal;
    unsigned s;
    arm_cal_nominal(&cal);
    for (s = 0; s < ARM_NUM_JOINTS; ++s) {
        int32_t lo, hi;
        float mid = (kArmServos[s].lo_deg + kArmServos[s].hi_deg) / 2.0f;
        /* Both ends of every joint range map inside 0..4095: no wrap through the encoder boundary. */
        CHECK(arm_to_raw(&cal, s, kArmServos[s].lo_deg, &lo) == 0);
        CHECK(arm_to_raw(&cal, s, kArmServos[s].hi_deg, &hi) == 0);
        CHECK(lo < hi && lo > 20 && hi < 4075);
        CHECK(fabsf(arm_from_raw(&cal, s, 2048) - mid) < 0.05f);
        {
            int32_t raw;
            CHECK(arm_to_raw(&cal, s, kArmServos[s].hi_deg + 400.0f, &raw) != 0); /* would wrap */
        }
    }
    /* Shoulder: 115 deg of joint = 345 deg of servo, with ~7 deg of spare at each end. */
    {
        int32_t lo, hi;
        (void)arm_to_raw(&cal, ARM_J_SHOULDER, -20, &lo);
        (void)arm_to_raw(&cal, ARM_J_SHOULDER, 95, &hi);
        CHECK(hi - lo >= 3925 && hi - lo <= 3930);
    }
}

int main(void) {
    test_single_joint_ranges();
    test_coupled_limits();
    test_random_agreement();
    test_step_recovery();
    test_speed_limits();
    test_calibration();
    TEST_FINISH("test_limits");
}
