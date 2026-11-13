/* BHMS Arm controller core: joint and tool motion with the safety limits enforced on the
 * device, E-stop and rail supervision, tool-change sequencing, telemetry cache.
 *
 * Everything runs from one cooperative loop: commands (arm_move, arm_enable, ...) validate and
 * start an operation without touching the bus (so they are safe inside a BHMS callback); the
 * work is done by arm_tick, which performs at most a few bus transactions per call and
 * must be called at >= 200 Hz. One operation at a time. No heap, no recursion, bounded.
 * Thread-safety: single owner (the main loop). */
#ifndef ARM_H
#define ARM_H

#include <stdint.h>

#include "arm_fault.h"
#include "arm_hw.h"
#include "arm_params.h"
#include "arm_limits.h"
#include "power.h"
#include "sts.h"
#include "tool_id.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ARM_ST_BOOT = 0,
    ARM_ST_NO_POWER,   /* USB only: VIN < 9 V. Not a fault. */
    ARM_ST_DISABLED,   /* rail off, E-stop released: `enable` allowed */
    ARM_ST_ENABLING,
    ARM_ST_READY,      /* rail on, torque on, holding */
    ARM_ST_MOVING,
    ARM_ST_PARKED,     /* rail on, torque released at the rest pose (or enable failed) */
    ARM_ST_ESTOP,      /* latched: rail cut; arm may have moved, re-home before use */
    ARM_ST_FAULT       /* latched fault, see fault code */
} arm_state;

typedef enum {
    ARM_OP_NONE = 0, ARM_OP_ENABLE, ARM_OP_MOVE, ARM_OP_HOME, ARM_OP_RELEASE,
    ARM_OP_TOOL_MOUNT, ARM_OP_TOOL_UNMOUNT, ARM_OP_GRIP, ARM_OP_TURN, ARM_OP_PRESS
} arm_op_kind;

typedef enum {
    TOOL_ST_NONE = 0,    /* nothing on the flange */
    TOOL_ST_DETECTED,    /* valid ID, unpowered */
    TOOL_ST_POWERING,
    TOOL_ST_READY,       /* powered, servo answered and configured */
    TOOL_ST_LOST,        /* ID went open-circuit while powered (hot unplug) */
    TOOL_ST_UNMOUNTING
} arm_tool_state;

/* Why a command was refused. `detail` names the limit (see limits.h) or the reason below. */
typedef enum {
    ARM_OK = 0,
    ARM_REFUSE_RANGE,         /* detail = limit code (limits.h) */
    ARM_REFUSE_INHIBITED,     /* detail = ARM_WHY_* */
    ARM_REFUSE_BUSY,
    ARM_REFUSE_PRECONDITION   /* detail = ARM_WHY_* */
} arm_refusal;

enum {
    ARM_WHY_NONE = 0,
    ARM_WHY_ESTOP_LATCHED = 1,   /* latched after an E-stop: explicit `enable` required */
    ARM_WHY_ESTOP_PRESSED = 2,   /* contact B shows the E-stop pressed or open */
    ARM_WHY_HARD_FAULT = 3,      /* contact A / Q2 fault: power cycle required */
    ARM_WHY_FAULT = 4,           /* latched fault: `enable` to retry */
    ARM_WHY_NOT_ENABLED = 5,     /* rail off or enabling: `enable` first */
    ARM_WHY_PARKED = 6,          /* torque released: `enable` first */
    ARM_WHY_NO_POWER = 7,        /* VIN below 9 V */
    ARM_WHY_NO_TOOL = 8,
    ARM_WHY_WRONG_TOOL = 9,
    ARM_WHY_TOOL_NOT_READY = 10,
    ARM_WHY_TOOL_MOUNTED = 11,   /* mount while mounted / unmount while not */
    ARM_WHY_TOOL_RESERVED = 12,  /* reserved or faulty tool ID */
    ARM_WHY_SENSE = 13,          /* INA219 not readable */
    ARM_WHY_STOPPING = 14        /* a stop is still being confirmed */
};

typedef struct {
    arm_op_kind kind;
    uint8_t status;       /* 0 completed, 1 failed, 2 canceled */
    uint8_t fault;        /* ARM_FAULT_* when failed */
    uint8_t measured;     /* the outcome was verified from the sensors */
    float values[3];      /* per-op results, see arm_device.c */
} arm_completion;

enum { ARM_DONE_COMPLETED = 0, ARM_DONE_FAILED = 1, ARM_DONE_CANCELED = 2 };

typedef struct {
    void *ctx;
    void (*finished)(void *ctx, const arm_completion *done);
    void (*progress)(void *ctx, uint8_t percent);
    void (*stop_confirmed)(void *ctx, uint8_t measured);
} arm_sink;

/* Cached servo telemetry (one block read per servo, round robin). */
typedef struct {
    uint8_t valid;
    uint8_t fail_count;
    uint8_t error;          /* status-packet error bits */
    uint8_t moving;
    uint8_t temp_c;
    uint8_t volt_dv;
    uint16_t current_ma;
    int16_t load_permille;
    float pos_deg;          /* joint angle / servo angle / knob output angle */
    float speed_dps;
    int32_t raw_steps;      /* raw position (signed steps for the knob) */
    uint32_t stamp_ms;
} arm_servo_state;

/* ---- Internal state (public so tests can inspect it; treat as read-only). ------- */
typedef struct arm {
    const arm_hw *hw;
    const arm_sink *sink;
    sts_bus bus;
    arm_cal cal;
    power_sup pwr;
    tool_id_filter tid;

    arm_state state;
    arm_op_kind op;
    uint8_t op_step, op_aux;
    uint32_t op_t0, op_t1;
    uint8_t fault_code;
    uint8_t pose_unknown;      /* the arm may have moved while unpowered: re-home */
    uint8_t torque_on;
    uint8_t stop_pending;
    uint8_t from_parked;
    uint32_t stop_t0;

    /* power sampling */
    uint32_t last_ina_ms, last_vin_ms, last_sense;
    uint32_t rail_mv, vin_mv;
    int32_t rail_ma;
    uint8_t ina_ok;
    uint8_t sense;

    /* trajectory */
    arm_pose q_cmd, q_start, q_goal;
    uint8_t traj_active;
    uint32_t traj_t0, traj_ms, traj_last_ms, progress_ms;
    uint8_t traj_pct, last_progress;
    uint8_t move_limit;        /* limit code of the last refusal / in-flight violation */
    float max_err_deg;

    /* servo telemetry and configuration */
    arm_servo_state sv[ARM_NUM_SERVOS];
    uint32_t last_scan_ms;
    uint8_t scan_next;
    uint8_t cfg_servo, cfg_phase, cfg_verify;
    uint8_t cfg_retry;

    /* tool */
    arm_tool_state tool_state;
    uint8_t tool_id;
    uint32_t tool_t0;
    int32_t knob_zero_steps;
    uint16_t fsr_base;
    float tool_target;         /* mm / deg / depth of the running tool op */
    float tool_peak;
    uint8_t tool_limit;
    uint32_t stall_t0;
    uint8_t stall_active;

    uint8_t led_last;
    uint8_t rail_applied;
    uint8_t freeze_servo;      /* 1 + servo index whose goal must be set to its position */
    uint8_t bus_fail;
    uint16_t servo_speed_steps; /* servo-side speed cap for the running motion */
} arm;

/* ---- Lifecycle ------------------------------------------------------------------ */
void arm_init(arm *a, const arm_hw *hw, const arm_cal *cal, const arm_sink *sink);
/* Advance the state machines. Bounded: at most one trajectory write plus one telemetry read
 * plus one configuration transaction per call. */
void arm_tick(arm *a);

/* ---- Commands. Each returns ARM_OK (operation started or done) or a refusal with `*detail`.
 * None touches the bus. ------------------------------------------------------------ */
arm_refusal arm_cmd_enable(arm *a, uint8_t *detail);
arm_refusal arm_cmd_move(arm *a, const float q[ARM_NUM_JOINTS], uint8_t speed_pct, uint8_t *detail);
arm_refusal arm_cmd_home(arm *a, uint8_t speed_pct, uint8_t *detail);
arm_refusal arm_cmd_hold(arm *a, uint8_t *detail);
arm_refusal arm_cmd_release(arm *a, uint8_t *detail);
arm_refusal arm_cmd_tool_mount(arm *a, uint8_t *detail);
arm_refusal arm_cmd_tool_unmount(arm *a, uint8_t *detail);
arm_refusal arm_cmd_grip(arm *a, float width_mm, uint8_t force_pct, uint8_t *detail);
arm_refusal arm_cmd_turn(arm *a, float angle_deg, uint8_t torque_permille, uint8_t *detail);
arm_refusal arm_cmd_press(arm *a, float depth_mm, uint8_t force_limit_pct, uint8_t *detail);

/* Cancel the running operation: the arm freezes where it is. Returns 1 when an operation was
 * running (it is reported CANCELED through the sink only if `report`). */
int arm_cancel(arm *a, int report);

typedef enum { ARM_STOP_INITIATED = 0, ARM_STOP_CONFIRMED = 1 } arm_stop_result;
/* STOP / E-stop reaction: abort motion and hold. Returns CONFIRMED when the device is already
 * safe; otherwise INITIATED and sink->stop_confirmed fires when the sensors say so. */
arm_stop_result arm_stop(arm *a, uint8_t *measured);

/* ---- Read-side accessors for the BHMS property table ----------------------------- */
/* Rail on, healthy and E-stop released: the servos can answer. */
int arm_servos_powered(const arm *a);
uint32_t arm_age_ms(const arm *a, const arm_servo_state *s);
uint8_t arm_estop_state(const arm *a);      /* estop_state: released/pressed/fault (measured) */
uint8_t arm_tool_present(const arm *a);
float arm_gripper_opening_mm(const arm *a, uint8_t *valid);
float arm_fsr_force_pct(const arm *a, uint8_t *valid);
float arm_knob_sensor_deg(const arm *a);

#ifdef __cplusplus
}
#endif
#endif
