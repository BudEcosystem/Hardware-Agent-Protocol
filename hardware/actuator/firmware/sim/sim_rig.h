/* Host simulation of the BHMS Arm controller board: eight STS3215-style servos on the
 * half-duplex bus (with echo), the E-stop loop and its rail, the INA219, the tool-ID divider,
 * AUX1 (FSR / AS5600), VIN and the status LED, behind the same arm_hw interface the RP2040
 * port implements. Test and simulator code only; nothing here ships in the firmware.
 *
 * The servo model implements what the firmware relies on: the packet format and checksums,
 * the register map of INTERFACE.md section 3, the EEPROM lock, servo-side angle windows,
 * goal speed, torque enable, the step (multi-turn) mode, Moving/Present_* telemetry, reboot
 * on rail loss. Time is manual (`sim_rig_advance`) so tests are deterministic.
 * Thread-safety: single owner. */
#ifndef SIM_RIG_H
#define SIM_RIG_H

#include <stddef.h>
#include <stdint.h>

#include "arm_hw.h"
#include "arm_params.h"

#define SIM_MEM 0x50u
#define SIM_RX_CAP 1024u
#define SIM_MAX_ID 8u

typedef struct {
    uint8_t ram[SIM_MEM];     /* control table; EEPROM part is mirrored in `eeprom` */
    uint8_t eeprom[SIM_MEM];
    uint8_t present;          /* installed (answers when powered) */
    uint8_t was_powered;
    double pos;               /* raw steps (signed steps in step mode) */
    double block_lo, block_hi;/* mechanical stops (object between fingers, FSR contact) */
    uint8_t stalled;
    uint32_t pings, reads, writes;
    double max_step_per_ms;   /* largest per-ms displacement observed */
    double speed_scale;       /* 1.0 normal; < 1 a sluggish joint (lag); 0 a jammed one */
    uint8_t err_bits;         /* status-packet error byte returned with every READ */
    uint8_t temp_c;
    unsigned drop_acks;       /* apply the next N WRITEs but swallow their ACK (lost reply) */
    int ignore_eeprom_writes; /* a servo whose EEPROM does not take writes (config must fail) */
} sim_servo;

typedef struct sim_rig {
    arm_hw hw;
    uint32_t now_ms;
    sim_servo sv[SIM_MAX_ID + 1u];
    uint8_t rx[SIM_RX_CAP];
    size_t rx_head, rx_len;
    /* GPIO and supplies */
    int servo_en_pin, tool_en_pin;
    int estop_pressed, contact_a_welded;
    int edge_arm, edge_bhms;
    double rail_mv;
    uint32_t vin_mv;
    int ina_fail;
    int extra_ma;             /* additional rail current (a stalled or shorted load) */
    double tool_r_id_ohm;     /* < 0: no tool */
    uint16_t aux1_code;
    uint16_t fsr_base;
    uint8_t led[3];
    /* Fault injection */
    int corrupt_echo_once, corrupt_echo_always;
    unsigned corrupt_sync_n;  /* damage the echo of the next N SYNC_WRITE frames */
    uint32_t drop_reply_mask; /* bit id: that servo does not answer */
    /* Statistics */
    uint32_t frames, bad_frames, led_changes, estop_cuts;
    uint32_t servo_en_log_on;
    int watchdog_reset;       /* the last reset was the watchdog */
    arm_cal saved_cal;        /* the calibration store (flash) */
    int cal_saved;
    unsigned cal_saves, cal_saves_while_powered;
    int falls;                /* times the arm lost the rail with torque on */
} sim_rig;

void sim_rig_init(sim_rig *r);
/* Advance simulated time by ms (1 ms steps). */
void sim_rig_advance(sim_rig *r, uint32_t ms);
void sim_rig_press_estop(sim_rig *r, int pressed);
/* Jam a servo where it is (a mechanical obstruction): it stops following its goal. */
void sim_rig_jam(sim_rig *r, unsigned id);
/* Mount a tool: R_ID in ohms (kArmTools), or < 0 to remove it. */
void sim_rig_set_tool(sim_rig *r, double r_id_ohm);
/* Servo helpers: position in raw steps, as the encoder would report. */
void sim_rig_place(sim_rig *r, unsigned id, double raw);
double sim_rig_pos(const sim_rig *r, unsigned id);
uint16_t sim_rig_reg16(const sim_rig *r, unsigned id, unsigned addr);
uint8_t sim_rig_reg8(const sim_rig *r, unsigned id, unsigned addr);

#endif
