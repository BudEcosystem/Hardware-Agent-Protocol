/* Joint, coupled and speed limit checks. The firmware enforces these itself; it never
 * trusts the host. A violation is reported as a limit code that doubles as the ERROR
 * `detail` byte of an OUT_OF_RANGE refusal:
 *   0..4      single-joint range of joint 0..4 (base_yaw .. wrist_roll)
 *   0x10..    coupled limit 0..2 (forearm_pitch, hairpin, tool_pitch)
 * Thread-safety: pure functions. */
#ifndef ARM_LIMITS_H
#define ARM_LIMITS_H

#include <stdint.h>

#include "arm_params.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ARM_LIMIT_NONE 0xFFu
#define ARM_LIMIT_COUPLED_BASE 0x10u

typedef struct {
    float q[ARM_NUM_JOINTS];
} arm_pose;

/* First violated limit of `p`, or ARM_LIMIT_NONE. A non-finite angle counts as a violation of
 * its own joint range. `margin_deg` tightens every limit (use 0 for commanded goals, a few
 * degrees for a measured pose). */
uint8_t arm_check_pose(const arm_pose *p, float margin_deg);

/* Worst violation of any joint range or coupled limit, in degrees beyond the nearest limit (0 when
 * inside every limit; a non-finite angle counts as 1000). *code receives the limit code of the worst
 * one, ARM_LIMIT_NONE when inside. Used to tell "worse" from "better" while recovering. */
float arm_pose_excess(const arm_pose *p, uint8_t *code);

/* "Cannot get worse, whichever joints fail to move": looks at the whole axis-aligned box spanned by
 * `from` and `to`, i.e. every pose in which each joint independently sits anywhere between its two
 * values. The straight path lies inside the box, and so does every real trajectory in which some
 * joints lag, stop short or do not move at all (a jammed joint). Returns the code of the first limit
 * whose violation somewhere in the box exceeds its violation at `from` by more than `tol_deg`, or
 * ARM_LIMIT_NONE when no limit can be violated more than it is at `from`. Exact for these limits
 * (each bounds one joint or a sum of joints, so the worst case is at a corner). A non-finite angle
 * returns its joint. */
uint8_t arm_check_box(const arm_pose *from, const arm_pose *to, float tol_deg);

/* Waypoint check for a motion that may start outside the limits (an arm moved by hand,
 * or encoder noise at a stop): `next` is allowed if it is inside every limit, or if each limit
 * it violates is violated by no more than at `prev`. Returns the first offending limit or
 * ARM_LIMIT_NONE. */
uint8_t arm_check_step(const arm_pose *prev, const arm_pose *next);

/* Human-readable name of a limit code ("base_yaw", "forearm_pitch", ...), or "unknown". */
const char *arm_limit_name(uint8_t code);

/* Sum of the joints of coupled limit k in pose p. */
float arm_coupled_sum(const arm_pose *p, unsigned k);

#ifdef __cplusplus
}
#endif
#endif
