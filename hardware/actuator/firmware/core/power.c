#include "power.h"

#include <string.h>

#include "arm_fault.h"

uint32_t ina219_bus_mv(uint16_t bus_reg) { return (uint32_t)(bus_reg >> 3) * 4u; }
int32_t ina219_current_ma(int16_t current_reg) { return ((int32_t)current_reg) / 4; }
uint32_t power_vin_mv(uint16_t adc12) {
    if (adc12 > 4095u) adc12 = 4095u;
    return ((uint32_t)adc12 * 3300u * 11u) / 4095u;
}

void power_init(power_sup *p) {
    memset(p, 0, sizeof *p);
    p->state = PWR_OFF;
}

static void set_state(power_sup *p, power_state s, uint32_t now) {
    p->state = s;
    p->t_state = now;
}

static void latch_fault(power_sup *p, uint8_t fault, power_state s, uint32_t now) {
    p->rail_cmd = 0;
    p->fault = fault;
    set_state(p, s, now);
}

void power_update(power_sup *p, const power_in *in) {
    uint32_t now = in->now_ms;

    /* ---- E-stop: the first thing, with no dependence on any other reading. */
    if (in->edge || in->sense) {
        p->rail_cmd = 0;
        if (!p->latched) {
            p->latched = 1;
            if (!p->hard_fault) latch_fault(p, ARM_FAULT_ESTOP, PWR_ESTOP, now);
        }
    }
    p->estop = p->hard_fault ? (uint8_t)ESTOP_FAULT : (in->sense ? (uint8_t)ESTOP_PRESSED
                                                                  : (uint8_t)ESTOP_RELEASED);

    /* Contact B high while the rail is still present: contact A welded or Q2 shorted. */
    if (in->sense && in->ina_ok && in->rail_mv > PWR_RAIL_DEAD_MV) {
        if (!p->fault_active) {
            p->fault_active = 1;
            p->t_estop_fault = now;
        } else if ((uint32_t)(now - p->t_estop_fault) > PWR_ESTOP_FAULT_MS && !p->hard_fault) {
            p->hard_fault = 1;
            p->estop = (uint8_t)ESTOP_FAULT;
            latch_fault(p, ARM_FAULT_ESTOP_CONTACT, PWR_FAULT, now);
        }
    } else {
        p->fault_active = 0;
    }

    if (p->hard_fault || p->latched) {
        p->rail_cmd = 0;
        if (p->state != PWR_ESTOP && p->state != PWR_FAULT)
            set_state(p, p->hard_fault ? PWR_FAULT : PWR_ESTOP, now);
        return;
    }

    /* INA219 health while the rail is commanded on. */
    if (p->rail_cmd) {
        if (in->ina_ok) p->ina_fail = 0;
        else if (++p->ina_fail >= PWR_INA_FAIL_LIMIT) {
            latch_fault(p, ARM_FAULT_POWER_SENSE, PWR_FAULT, now);
            return;
        }
    } else {
        p->ina_fail = 0;
    }

    switch (p->state) {
    case PWR_ST_RISE:
        if ((uint32_t)(now - p->t_state) >= PWR_SELFTEST_MS) {
            if (!in->ina_ok || in->rail_mv <= PWR_SELFTEST_UP_MV) {
                latch_fault(p, ARM_FAULT_SELFTEST, PWR_FAULT, now);
            } else {
                p->rail_cmd = 0;
                set_state(p, PWR_ST_FALL, now);
            }
        }
        break;
    case PWR_ST_FALL:
        if (in->ina_ok && in->rail_mv < PWR_RAIL_DEAD_MV) {
            p->selftest_done = 1;
            p->rail_cmd = 1;
            set_state(p, PWR_RAMP, now);
        } else if ((uint32_t)(now - p->t_state) > PWR_SELFTEST_MS) {
            latch_fault(p, ARM_FAULT_SELFTEST, PWR_FAULT, now);
        }
        break;
    case PWR_RAMP:
        if (in->ina_ok && in->rail_mv >= PWR_RAIL_OK_MV) set_state(p, PWR_ON, now);
        else if ((uint32_t)(now - p->t_state) > PWR_RAMP_MS)
            latch_fault(p, ARM_FAULT_SERVO_RAIL, PWR_FAULT, now);
        break;
    case PWR_ON:
        if (in->ina_ok && in->rail_mv < PWR_RAIL_OK_MV) {
            /* Contact released, SERVO_EN high, rail low: loop open, fuse or supply. */
            latch_fault(p, ARM_FAULT_SERVO_RAIL, PWR_FAULT, now);
            break;
        }
        if (in->ina_ok && in->rail_ma > PWR_OVERCURRENT_MA) {
            if (!p->over_active) {
                p->over_active = 1;
                p->t_over = now;
            } else if ((uint32_t)(now - p->t_over) >= PWR_OVERCURRENT_MS) {
                latch_fault(p, ARM_FAULT_OVERCURRENT, PWR_FAULT, now);
                break;
            }
        } else {
            p->over_active = 0;
        }
        if (in->ina_ok && in->rail_ma > PWR_WARN_MA) {
            if (!p->warn_active) {
                p->warn_active = 1;
                p->t_warn = now;
            } else if ((uint32_t)(now - p->t_warn) >= PWR_WARN_MS) {
                p->warn_overcurrent = 1;
            }
        } else {
            p->warn_active = 0;
            p->warn_overcurrent = 0;
        }
        break;
    case PWR_OFF:
    case PWR_ESTOP:
    case PWR_FAULT:
    default:
        break;
    }
}

int power_request_enable(power_sup *p, const power_in *in) {
    if (p->hard_fault) return PWR_REFUSE_HARD_FAULT;
    if (in->sense) return PWR_REFUSE_ESTOP;
    if (in->vin_mv < PWR_VIN_MIN_MV) return PWR_REFUSE_NO_POWER;
    if (p->state == PWR_ON) return PWR_ENABLE_OK; /* already on (re-run of the arm sequence) */
    if (p->state == PWR_ST_RISE || p->state == PWR_ST_FALL || p->state == PWR_RAMP)
        return PWR_REFUSE_BUSY;
    if (!in->ina_ok) return PWR_REFUSE_SENSE;
    /* Leaving the latch: only here, with the contact released. */
    p->latched = 0;
    p->fault = ARM_FAULT_NONE;
    p->over_active = p->warn_active = p->warn_overcurrent = 0;
    p->ina_fail = 0;
    if (!p->selftest_done) {
        p->rail_cmd = 1;
        set_state(p, PWR_ST_RISE, in->now_ms);
    } else {
        p->rail_cmd = 1;
        set_state(p, PWR_RAMP, in->now_ms);
    }
    return PWR_ENABLE_OK;
}

void power_request_disable(power_sup *p) {
    p->rail_cmd = 0;
    if (p->state != PWR_ESTOP && p->state != PWR_FAULT) p->state = PWR_OFF;
}

void power_clear_fault(power_sup *p) {
    if (p->hard_fault) return;
    p->fault = ARM_FAULT_NONE;
    if (p->state == PWR_FAULT) p->state = PWR_OFF;
}
