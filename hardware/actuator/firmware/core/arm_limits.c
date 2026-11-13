#include "arm_limits.h"

#include <math.h>

float arm_coupled_sum(const arm_pose *p, unsigned k) {
    float s = 0.0f;
    unsigned i;
    for (i = 0; i < kArmCoupled[k].n_joints; ++i) s += p->q[kArmCoupled[k].joints[i]];
    return s;
}

uint8_t arm_check_pose(const arm_pose *p, float margin_deg) {
    unsigned j, k;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float q = p->q[j];
        if (!isfinite(q) || q < kArmServos[j].lo_deg + margin_deg ||
            q > kArmServos[j].hi_deg - margin_deg)
            return (uint8_t)j;
    }
    for (k = 0; k < ARM_NUM_COUPLED; ++k) {
        float s = arm_coupled_sum(p, k);
        if (s < kArmCoupled[k].lo_deg + margin_deg || s > kArmCoupled[k].hi_deg - margin_deg)
            return (uint8_t)(ARM_LIMIT_COUPLED_BASE + k);
    }
    return ARM_LIMIT_NONE;
}

float arm_pose_excess(const arm_pose *p, uint8_t *code) {
    float worst = 0.0f;
    unsigned j, k;
    *code = ARM_LIMIT_NONE;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float q = p->q[j], e;
        if (!isfinite(q)) {
            *code = (uint8_t)j;
            return 1000.0f;
        }
        e = q < kArmServos[j].lo_deg ? kArmServos[j].lo_deg - q : (q > kArmServos[j].hi_deg ? q - kArmServos[j].hi_deg : 0.0f);
        if (e > worst) {
            worst = e;
            *code = (uint8_t)j;
        }
    }
    for (k = 0; k < ARM_NUM_COUPLED; ++k) {
        float s = arm_coupled_sum(p, k), e;
        e = s < kArmCoupled[k].lo_deg ? kArmCoupled[k].lo_deg - s : (s > kArmCoupled[k].hi_deg ? s - kArmCoupled[k].hi_deg : 0.0f);
        if (e > worst) {
            worst = e;
            *code = (uint8_t)(ARM_LIMIT_COUPLED_BASE + k);
        }
    }
    return worst;
}

static float over(float lo_val, float hi_val, float lo_lim, float hi_lim) {
    float e = 0.0f;
    if (lo_lim - lo_val > e) e = lo_lim - lo_val;
    if (hi_val - hi_lim > e) e = hi_val - hi_lim;
    return e;
}

uint8_t arm_check_box(const arm_pose *from, const arm_pose *to, float tol_deg) {
    unsigned j, k, i;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float f = from->q[j], t = to->q[j];
        float lo = f < t ? f : t, hi = f < t ? t : f;
        if (!isfinite(f) || !isfinite(t)) return (uint8_t)j;
        if (over(lo, hi, kArmServos[j].lo_deg, kArmServos[j].hi_deg) >
            over(f, f, kArmServos[j].lo_deg, kArmServos[j].hi_deg) + tol_deg)
            return (uint8_t)j;
    }
    for (k = 0; k < ARM_NUM_COUPLED; ++k) {
        float lo = 0.0f, hi = 0.0f, s = 0.0f;
        for (i = 0; i < kArmCoupled[k].n_joints; ++i) {
            float f = from->q[kArmCoupled[k].joints[i]], t = to->q[kArmCoupled[k].joints[i]];
            s += f;
            lo += f < t ? f : t;
            hi += f < t ? t : f;
        }
        if (over(lo, hi, kArmCoupled[k].lo_deg, kArmCoupled[k].hi_deg) >
            over(s, s, kArmCoupled[k].lo_deg, kArmCoupled[k].hi_deg) + tol_deg)
            return (uint8_t)(ARM_LIMIT_COUPLED_BASE + k);
    }
    return ARM_LIMIT_NONE;
}

uint8_t arm_check_step(const arm_pose *prev, const arm_pose *next) {
    unsigned j, k;
    for (j = 0; j < ARM_NUM_JOINTS; ++j) {
        float q = next->q[j], p = prev->q[j];
        float lo = kArmServos[j].lo_deg, hi = kArmServos[j].hi_deg;
        if (!isfinite(q)) return (uint8_t)j;
        if (q < lo && !(p < lo && q >= p)) return (uint8_t)j; /* may only come back inside */
        if (q > hi && !(p > hi && q <= p)) return (uint8_t)j;
    }
    for (k = 0; k < ARM_NUM_COUPLED; ++k) {
        float s = arm_coupled_sum(next, k), sp = arm_coupled_sum(prev, k);
        float lo = kArmCoupled[k].lo_deg, hi = kArmCoupled[k].hi_deg;
        if (s < lo && !(sp < lo && s >= sp)) return (uint8_t)(ARM_LIMIT_COUPLED_BASE + k);
        if (s > hi && !(sp > hi && s <= sp)) return (uint8_t)(ARM_LIMIT_COUPLED_BASE + k);
    }
    return ARM_LIMIT_NONE;
}

const char *arm_limit_name(uint8_t code) {
    if (code < ARM_NUM_JOINTS) return kArmServos[code].name;
    if (code >= ARM_LIMIT_COUPLED_BASE && code < ARM_LIMIT_COUPLED_BASE + ARM_NUM_COUPLED)
        return kArmCoupled[code - ARM_LIMIT_COUPLED_BASE].name;
    return "unknown";
}
