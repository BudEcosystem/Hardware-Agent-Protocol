#include "arm_params.h"

#include <math.h>

/* Tool servos: the gripper rack moves 30 mm per finger (143.2 deg of servo), the knob is
 * multi-turn (no angle limit), the presser cam turns 0..180 deg. */
const arm_servo_spec kArmServos[ARM_NUM_SERVOS] = {
    {"base_yaw", 1, -150.0f, 150.0f, 1.0f, 1000u},
    /* 78 % of stall: a design requirement (docs/design.md section 4), not a recommendation. */
    {"shoulder_pitch", 2, -20.0f, 95.0f, 3.0f, 780u},
    {"elbow_pitch", 3, -5.0f, 125.0f, 2.0f, 1000u},
    {"wrist_pitch", 4, -100.0f, 100.0f, 1.0f, 1000u},
    {"wrist_roll", 5, -150.0f, 150.0f, 1.0f, 1000u},
    {"gripper", 6, 0.0f, 143.239f, 1.0f, 150u},
    {"knob_turner", 7, 0.0f, 0.0f, 2.0f, 25u},
    {"button_presser", 8, 0.0f, 180.0f, 1.0f, 200u},
};

const arm_coupled_spec kArmCoupled[ARM_NUM_COUPLED] = {
    {"forearm_pitch", 2, {ARM_J_SHOULDER, ARM_J_ELBOW, 0}, -180.0f, 175.0f},
    {"hairpin", 2, {ARM_J_ELBOW, ARM_J_WRIST_PITCH, 0}, -180.0f, 165.0f},
    {"tool_pitch", 3, {ARM_J_SHOULDER, ARM_J_ELBOW, ARM_J_WRIST_PITCH}, -180.0f, 183.0f},
};

const float kArmRestPose[ARM_NUM_JOINTS] = {0.0f, 30.0f, 90.0f, 45.0f, 0.0f};

const arm_tool_spec kArmTools[8] = {
    {1, "gripper", 1000.0f},      {2, "knob_turner", 3300.0f}, {3, "button_presser", 10000.0f},
    {4, "slider_pusher", 33000.0f}, {5, "reserved", 2000.0f},  {6, "reserved", 5600.0f},
    {7, "reserved", 18000.0f},    {8, "reserved", 100000.0f},
};

void arm_cal_nominal(arm_cal *cal) {
    unsigned s;
    for (s = 0; s < ARM_NUM_SERVOS; ++s) {
        const arm_servo_spec *sp = &kArmServos[s];
        float centre = (sp->lo_deg + sp->hi_deg) * 0.5f;
        cal->sign[s] = 1;
        /* Joints: centre of the range at raw 2048. Tool servos: range start at raw 1024
         * (a gripper/presser at its closed stop; the knob at its mount position). */
        if (s < ARM_NUM_JOINTS)
            cal->raw_zero[s] =
                (int16_t)lroundf(2048.0f - centre * sp->ratio * ARM_SERVO_COUNTS / 360.0f);
        else
            cal->raw_zero[s] = (s == ARM_S_KNOB) ? 0 : 1024; /* knob: step mode, relative */
    }
}

int arm_to_raw(const arm_cal *cal, unsigned servo, float deg, int32_t *raw) {
    float r;
    if (servo >= ARM_NUM_SERVOS || cal == 0 || raw == 0 || !isfinite(deg)) return -1;
    r = (float)cal->raw_zero[servo] +
        (float)cal->sign[servo] * deg * kArmServos[servo].ratio * ARM_SERVO_COUNTS / 360.0f;
    if (r < 0.0f || r > ARM_SERVO_COUNTS - 1.0f) return -1;
    *raw = (int32_t)lroundf(r);
    return 0;
}

float arm_from_raw(const arm_cal *cal, unsigned servo, int32_t raw) {
    return (float)cal->sign[servo] * (float)(raw - cal->raw_zero[servo]) * 360.0f /
           ARM_SERVO_COUNTS / kArmServos[servo].ratio;
}

float arm_speed_limit_dps(unsigned servo) {
    return ARM_SERVO_NOLOAD_RAD_S * (180.0f / 3.14159265358979f) / kArmServos[servo].ratio;
}
