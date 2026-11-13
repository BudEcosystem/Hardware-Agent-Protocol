/* Servo-rail and E-stop supervisor (INTERFACE.md sections 2, 4, 6).
 *
 * The hardware path (contact A -> Q2 gate) cuts the rail without firmware. This module is
 * the firmware half: it latches the E-stop (restart inhibit), derives the measured
 * `released/pressed/fault` state from contact B plus the INA219 rail readings, runs the
 * boot self-test, and decides when SERVO_EN must be cleared (E-stop, rail fault,
 * overcurrent). It owns the rail command; the caller applies `rail_cmd` to the GPIO.
 * Thread-safety: single owner. */
#ifndef ARM_POWER_H
#define ARM_POWER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Thresholds from INTERFACE.md --------------------------------------------- */
#define PWR_RAIL_OK_MV 9000u        /* rail below this while enabled and released: fault */
#define PWR_RAIL_DEAD_MV 2000u      /* rail above this with the E-stop open: contact A / Q2 */
#define PWR_SELFTEST_UP_MV 10000u   /* rail must exceed this 50 ms after enabling */
#define PWR_SELFTEST_MS 50u
#define PWR_ESTOP_FAULT_MS 20u
#define PWR_RAMP_MS 100u            /* grace for the rail to rise after enabling */
#define PWR_VIN_MIN_MV 9000u        /* below: "no actuator power" */
#define PWR_OVERCURRENT_MA 4500
#define PWR_OVERCURRENT_MS 100u
#define PWR_WARN_MA 3000
#define PWR_WARN_MS 1000u
#define PWR_INA_FAIL_LIMIT 20u      /* consecutive failed INA219 reads while the rail is on */

/* INA219 (INTERFACE.md section 6): config 0x299F, calibration 0x4000, 4 mV and 0.25 mA LSB. */
#define INA219_CONFIG 0x299Fu
#define INA219_CALIBRATION 0x4000u
uint32_t ina219_bus_mv(uint16_t bus_reg);
int32_t ina219_current_ma(int16_t current_reg);
/* VIN = V_adc x 11 (100 k / 10 k divider, 3.3 V reference, 12-bit). */
uint32_t power_vin_mv(uint16_t adc12);

typedef enum {
    PWR_OFF = 0,     /* rail off, nothing pending */
    PWR_ST_RISE,     /* self-test: rail on, waiting 50 ms */
    PWR_ST_FALL,     /* self-test: rail off, waiting for < 2 V */
    PWR_RAMP,        /* rail commanded on, waiting for >= 9 V */
    PWR_ON,          /* rail on and healthy */
    PWR_ESTOP,       /* latched: needs an explicit enable with the contact released */
    PWR_FAULT        /* latched fault; see fault code */
} power_state;

typedef enum { ESTOP_RELEASED = 0, ESTOP_PRESSED = 1, ESTOP_FAULT = 2 } estop_state;

typedef struct {
    uint32_t now_ms;
    uint8_t sense;     /* GPIO8 level: 1 = pressed/open */
    uint8_t edge;      /* a rising edge was latched by the IRQ since the last call */
    uint8_t ina_ok;    /* rail_mv / rail_ma are valid this call */
    uint32_t rail_mv;
    int32_t rail_ma;
    uint32_t vin_mv;
} power_in;

typedef struct {
    power_state state;
    uint8_t rail_cmd;          /* desired SERVO_EN level */
    uint8_t latched;           /* E-stop latch (restart inhibit) */
    uint8_t hard_fault;        /* contact A / Q2 fault: cleared only by a power cycle */
    uint8_t fault;             /* ARM_FAULT_* of the last latched fault, 0 = none */
    uint8_t selftest_done;
    uint8_t warn_overcurrent;  /* > 3 A for 1 s (informational) */
    uint8_t estop;             /* estop_state, measured */
    uint8_t ina_fail;
    uint32_t t_state, t_estop_fault, t_over, t_warn;
    uint8_t over_active, warn_active, fault_active;
} power_sup;

typedef enum {
    PWR_ENABLE_OK = 0,
    PWR_REFUSE_ESTOP = 1,      /* contact pressed / open */
    PWR_REFUSE_HARD_FAULT = 2, /* contact A / Q2 fault latched */
    PWR_REFUSE_NO_POWER = 3,   /* VIN below 9 V */
    PWR_REFUSE_BUSY = 4,       /* a self-test or ramp is in progress */
    PWR_REFUSE_SENSE = 5       /* INA219 not readable */
} power_enable_result;

void power_init(power_sup *p);
/* Evaluate one sample. Call at >= 100 Hz; the E-stop reaction (rail_cmd -> 0) happens in the
 * same call that sees the edge or the high level. */
void power_update(power_sup *p, const power_in *in);
/* Explicit enable (the only way out of the latch). Starts the boot self-test the first time. */
int power_request_enable(power_sup *p, const power_in *in);
/* Deliberate rail cut after the arm was parked (not an E-stop): clears the rail command. */
void power_request_disable(power_sup *p);
/* Clear a soft fault (not a hard fault) so enable may be tried again. */
void power_clear_fault(power_sup *p);

#ifdef __cplusplus
}
#endif
#endif
