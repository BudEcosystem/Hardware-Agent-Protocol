/* BHMS Arm: the fixed numbers the firmware enforces (joint ranges, ratios,
 * coupled limits, torque caps, speed limits, tool IDs). They mirror
 * hardware/actuator/cad/params.py, which wins on disagreement; tests/test_params_sync.py
 * fails when the two drift. Plain const data, no heap, C99.
 * Thread-safety: read-only after start-up. */
#ifndef ARM_PARAMS_H
#define ARM_PARAMS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ARM_NUM_JOINTS 5u /* base_yaw .. wrist_roll: servo IDs 1..5 */
#define ARM_NUM_SERVOS 8u /* plus the tool servos 6 (gripper), 7 (knob), 8 (presser) */
#define ARM_SERVO_COUNTS 4096.0f
#define ARM_NUM_COUPLED 3u
#define ARM_MAX_COUPLED_JOINTS 3u

enum { ARM_J_BASE_YAW = 0, ARM_J_SHOULDER, ARM_J_ELBOW, ARM_J_WRIST_PITCH, ARM_J_WRIST_ROLL };
enum { ARM_S_GRIPPER = 5, ARM_S_KNOB = 6, ARM_S_PRESSER = 7 }; /* servo table index */

/* Joint (or tool-servo) description. For tool servos lo/hi are the travel in degrees of
 * the servo shaft from the calibrated zero (ratio 1.0). */
typedef struct {
    const char *name;
    uint8_t servo_id;
    float lo_deg, hi_deg;     /* range of the quantity the servo moves */
    float ratio;              /* servo turns per joint turn */
    uint16_t torque_permille; /* Max_Torque_Limit, 0..1000 of stall */
} arm_servo_spec;

extern const arm_servo_spec kArmServos[ARM_NUM_SERVOS];

/* Coupled limit: the sum of the listed joint angles must stay inside [lo, hi]. The lower
 * side is unreachable inside the single-joint ranges; it is stored as -180 like params.py. */
typedef struct {
    const char *name;
    uint8_t n_joints;
    uint8_t joints[ARM_MAX_COUPLED_JOINTS];
    float lo_deg, hi_deg;
} arm_coupled_spec;

extern const arm_coupled_spec kArmCoupled[ARM_NUM_COUPLED];

/* Servo no-load speed (rad/s at the servo shaft; cad/params.py Servo.no_load_speed_rad_s). */
#define ARM_SERVO_NOLOAD_RAD_S 4.7f
/* Rest pose (INTERFACE.md section 4): forearm on the support. */
extern const float kArmRestPose[ARM_NUM_JOINTS];
/* Margin (degrees) applied to a *measured* pose before the first torque-enable. */
#define ARM_ENABLE_MARGIN_DEG 3.0f

/* Tool identity (cad/params.py Tools.tool_ids): the R_ID of each code and the pull-up. */
typedef struct {
    uint8_t code;
    const char *name;
    float r_id_ohm;
} arm_tool_spec;
extern const arm_tool_spec kArmTools[8];
#define ARM_TOOL_PULLUP_OHM 10000.0f
enum {
    ARM_TOOL_NONE = 0,
    ARM_TOOL_GRIPPER = 1,
    ARM_TOOL_KNOB_TURNER = 2,
    ARM_TOOL_BUTTON_PRESSER = 3,
    ARM_TOOL_SLIDER_PUSHER = 4,
    ARM_TOOL_FAULT = 0xFE /* short circuit on the ID pin */
};

/* Tool geometry (Tools in params.py / INTERFACE.md 3.1). */
#define ARM_GRIPPER_STROKE_MM 30.0f   /* per finger */
#define ARM_GRIPPER_PINION_R_MM 12.0f /* rack radius: finger travel = r * servo angle (rad) */
#define ARM_KNOB_RATIO 2.0f           /* 20:40 spur: servo turns per knob turn */
/* Knob output range +-1000 deg = +-22 756 counts; the mount position (any value) is the zero, and
 * zero + target must stay inside +-28 000 counts (about +-7 servo turns, +-28 672): arm_cmd_turn checks. */
#define ARM_KNOB_MAX_DEG 1000.0f
#define ARM_KNOB_MAX_COUNTS 28000
#define ARM_PRESSER_STROKE_MM 8.0f    /* cam: depth = 4 mm * (1 - cos(servo angle)) */
#define ARM_PRESSER_THROW_MM 4.0f

/* Per-servo calibration: joint = sign * (raw - raw_zero) * 360 / 4096 / ratio. */
typedef struct {
    int16_t raw_zero[ARM_NUM_SERVOS];
    int8_t sign[ARM_NUM_SERVOS];
} arm_cal;

/* Nominal calibration: the middle of every joint range sits at raw 2048, so the servo's
 * single-turn wrap point lies outside the joint range (INTERFACE.md 3.1). */
void arm_cal_nominal(arm_cal *cal);
/* Convert a quantity (degrees of the moved joint/shaft) to a raw count. Returns 0, or -1
 * when the result is outside 0..4095 (it would wrap through the encoder boundary). */
int arm_to_raw(const arm_cal *cal, unsigned servo, float deg, int32_t *raw);
float arm_from_raw(const arm_cal *cal, unsigned servo, int32_t raw);
/* Joint speed limit in deg/s at 100 %: servo no-load speed divided by the ratio. */
float arm_speed_limit_dps(unsigned servo);

#ifdef __cplusplus
}
#endif
#endif
