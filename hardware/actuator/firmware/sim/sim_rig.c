#include "sim_rig.h"

#include <math.h>
#include <string.h>

#include "arm_params.h"
#include "power.h"
#include "sts.h"

#define kNoLoadSteps 3064.0 /* 4.7 rad/s */

static int powered(const sim_rig *r) { return r->rail_mv > 9000.0; }

/* ---- Servo memory --------------------------------------------------------------------- */
static uint16_t rg16(const sim_servo *s, unsigned a) { return (uint16_t)(s->ram[a] | (s->ram[a + 1u] << 8)); }
static void wr16(sim_servo *s, unsigned a, uint16_t v) { s->ram[a] = (uint8_t)v; s->ram[a + 1u] = (uint8_t)(v >> 8); }

static void servo_reset_ram(sim_servo *s) {
    memcpy(s->ram, s->eeprom, SIM_MEM);
    s->ram[STS_REG_TORQUE_ENABLE] = 0;
    s->ram[STS_REG_LOCK] = 1;
    wr16(s, STS_REG_TORQUE_LIMIT, rg16(s, STS_REG_MAX_TORQUE));
    s->stalled = 0;
}

/* Multi-turn absolute operation (the knob): position mode with both angle limits 0, goal and
 * present position as sign-magnitude counts. The relative step mode (3) is deliberately not
 * modelled: the firmware must never select it. */
static int step_mode(const sim_servo *s) {
    return s->ram[STS_REG_OPERATING_MODE] == STS_MODE_POSITION && rg16(s, STS_REG_MIN_ANGLE) == 0 &&
           rg16(s, STS_REG_MAX_ANGLE) == 0;
}

static void servo_write(sim_servo *s, unsigned addr, const uint8_t *d, size_t n) {
    size_t i;
    for (i = 0; i < n && addr + i < SIM_MEM; ++i) {
        unsigned a = (unsigned)(addr + i);
        if (a < 0x28u && a != STS_REG_LOCK && (s->ram[STS_REG_LOCK] == 1u || s->ignore_eeprom_writes))
            continue; /* EEPROM locked */
        s->ram[a] = d[i];
        if (a < 0x28u && s->ram[STS_REG_LOCK] == 0u) s->eeprom[a] = d[i];
    }
    if (addr <= STS_REG_LOCK && addr + n > STS_REG_LOCK && s->ram[STS_REG_LOCK] == 1u) {
        /* lock re-engaged: nothing to do, writes are gated above */
    }
    ++s->writes;
}

static void servo_tick(sim_rig *r, sim_servo *s) {
    double goal, lo, hi, v, step, before = s->pos;
    int on = powered(r) && s->present;
    if (!on) {
        if (s->was_powered) {
            if (s->ram[STS_REG_TORQUE_ENABLE]) ++r->falls;
            servo_reset_ram(s); /* the servo reboots when the rail returns */
        }
        s->was_powered = 0;
        return;
    }
    if (!s->was_powered) {
        s->was_powered = 1;
        servo_reset_ram(s);
    }
    if (!s->ram[STS_REG_TORQUE_ENABLE]) {
        s->stalled = 0;
        return;
    }
    if (step_mode(s)) {
        goal = (double)sts_sm_decode(rg16(s, STS_REG_GOAL_POSITION), 15);
    } else {
        goal = (double)(rg16(s, STS_REG_GOAL_POSITION) & 0x0FFFu);
        lo = rg16(s, STS_REG_MIN_ANGLE);
        hi = rg16(s, STS_REG_MAX_ANGLE);
        if (hi > lo) goal = goal < lo ? lo : (goal > hi ? hi : goal); /* servo-side window */
    }
    v = rg16(s, STS_REG_GOAL_SPEED);
    if (v <= 0.0 || v > kNoLoadSteps) v = kNoLoadSteps;
    v *= s->speed_scale;
    step = v / 1000.0;
    if (fabs(goal - s->pos) <= step) s->pos = goal;
    else s->pos += goal > s->pos ? step : -step;
    s->stalled = 0;
    if (s->pos > s->block_hi) { s->pos = s->block_hi; s->stalled = 1; }
    if (s->pos < s->block_lo) { s->pos = s->block_lo; s->stalled = 1; }
    if (fabs(s->pos - before) > s->max_step_per_ms) s->max_step_per_ms = fabs(s->pos - before);
}

/* Telemetry registers 0x38..0x46 derived from the dynamics. */
static void servo_telemetry(sim_servo *s) {
    double err;
    int32_t raw = (int32_t)llround(s->pos);
    int moving;
    if (step_mode(s)) wr16(s, STS_REG_PRESENT_POSITION, sts_sm_encode(raw, 15));
    else wr16(s, STS_REG_PRESENT_POSITION, (uint16_t)(raw < 0 ? 0 : (raw > 4095 ? 4095 : raw)));
    err = s->ram[STS_REG_TORQUE_ENABLE]
              ? fabs((step_mode(s) ? (double)sts_sm_decode(rg16(s, STS_REG_GOAL_POSITION), 15)
                                   : (double)(rg16(s, STS_REG_GOAL_POSITION) & 0x0FFFu)) - s->pos)
              : 0.0;
    moving = s->ram[STS_REG_TORQUE_ENABLE] && err >= 2.0 && !s->stalled;
    s->ram[STS_REG_MOVING] = (uint8_t)moving;
    wr16(s, STS_REG_PRESENT_SPEED, moving ? sts_sm_encode(1000, 15) : 0u);
    wr16(s, STS_REG_PRESENT_LOAD, sts_sm_encode(s->stalled ? 300 : (moving ? 120 : 20), 10));
    s->ram[STS_REG_PRESENT_VOLTAGE] = 120;
    s->ram[STS_REG_PRESENT_TEMP] = s->temp_c;
    wr16(s, STS_REG_PRESENT_CURRENT, (uint16_t)(moving ? 40 : 5));
}

/* ---- Bus ------------------------------------------------------------------------------------ */
static void rx_push(sim_rig *r, const uint8_t *b, size_t n) {
    size_t i;
    for (i = 0; i < n && r->rx_len < SIM_RX_CAP; ++i)
        r->rx[(r->rx_head + r->rx_len++) % SIM_RX_CAP] = b[i];
}

static void reply_err(sim_rig *r, uint8_t id, uint8_t err, const uint8_t *params, size_t n) {
    uint8_t f[STS_FRAME_MAX];
    f[0] = 0xFF;
    f[1] = 0xFF;
    f[2] = id;
    f[3] = (uint8_t)(n + 2u);
    f[4] = err;
    if (n) memcpy(&f[5], params, n);
    f[5 + n] = sts_checksum(&f[2], n + 3u);
    rx_push(r, f, n + 6u);
}

static void reply(sim_rig *r, uint8_t id, const uint8_t *params, size_t n) { reply_err(r, id, 0, params, n); }

static void bus_frame(sim_rig *r, const uint8_t *f, size_t n) {
    uint8_t id, len, instr;
    const uint8_t *p;
    size_t np;
    if (n < 6u || f[0] != 0xFF || f[1] != 0xFF || sts_checksum(&f[2], n - 3u) != f[n - 1u]) {
        ++r->bad_frames;
        return;
    }
    ++r->frames;
    id = f[2];
    len = f[3];
    instr = f[4];
    p = &f[5];
    np = (size_t)len - 2u;
    if (id == STS_BROADCAST_ID) {
        if (instr == STS_INSTR_SYNC_WRITE && np >= 2u) {
            uint8_t addr = p[0], per = p[1];
            size_t k = 2u;
            while (per != 0u && k + 1u + per <= np) {
                unsigned sid = p[k];
                if (sid >= 1u && sid <= SIM_MAX_ID && powered(r) && r->sv[sid].present &&
                    (sid <= ARM_NUM_JOINTS || r->tool_en_pin))
                    servo_write(&r->sv[sid], addr, &p[k + 1u], per);
                k += 1u + per;
            }
        }
        return;
    }
    if (id < 1u || id > SIM_MAX_ID) return;
    {
        sim_servo *s = &r->sv[id];
        if (!s->present || !powered(r) || (r->drop_reply_mask & (1u << id)) != 0u) return;
        if (id > ARM_NUM_JOINTS && !r->tool_en_pin) return; /* tool servos sit behind Q3 */
        switch (instr) {
        case STS_INSTR_PING:
            ++s->pings;
            reply(r, id, 0, 0);
            break;
        case STS_INSTR_READ:
            if (np == 2u && p[0] + (unsigned)p[1] <= SIM_MEM) {
                servo_telemetry(s);
                ++s->reads;
                reply_err(r, id, s->err_bits, &s->ram[p[0]], p[1]);
            }
            break;
        case STS_INSTR_WRITE:
            if (np >= 2u) {
                servo_write(s, p[0], &p[1], np - 1u);
                if (s->drop_acks > 0) --s->drop_acks; /* applied, but the ACK is lost */
                else reply(r, id, 0, 0);
            }
            break;
        default:
            break;
        }
    }
}

static void h_bus_flush(void *c) {
    sim_rig *r = (sim_rig *)c;
    r->rx_len = 0;
}
static void h_bus_write(void *c, const uint8_t *buf, size_t n) {
    sim_rig *r = (sim_rig *)c;
    uint8_t echo[STS_FRAME_MAX];
    memcpy(echo, buf, n < sizeof echo ? n : sizeof echo);
    if (r->corrupt_sync_n > 0 && n > 4 && buf[4] == STS_INSTR_SYNC_WRITE) {
        --r->corrupt_sync_n;
        r->corrupt_echo_once = 1;
    }
    if ((r->corrupt_echo_once || r->corrupt_echo_always) && n > 0) {
        echo[n - 1u] ^= 0x55;
        r->corrupt_echo_once = 0;
    }
    rx_push(r, echo, n < sizeof echo ? n : sizeof echo);
    bus_frame(r, buf, n);
}
static size_t h_bus_read(void *c, uint8_t *buf, size_t n, uint32_t timeout_us) {
    sim_rig *r = (sim_rig *)c;
    size_t i;
    (void)timeout_us;
    for (i = 0; i < n && r->rx_len > 0; ++i) {
        buf[i] = r->rx[r->rx_head];
        r->rx_head = (r->rx_head + 1u) % SIM_RX_CAP;
        --r->rx_len;
    }
    return i;
}

/* ---- GPIO, ADC, INA219 ------------------------------------------------------------------ */
static uint32_t h_millis(void *c) { return ((sim_rig *)c)->now_ms; }
static void h_servo_en(void *c, int on) { ((sim_rig *)c)->servo_en_pin = on != 0; }
static void h_tool_en(void *c, int on) { ((sim_rig *)c)->tool_en_pin = on != 0; }
static int h_sense(void *c) { return ((sim_rig *)c)->estop_pressed; }
static int h_edge(void *c) {
    sim_rig *r = (sim_rig *)c;
    int e = r->edge_arm;
    r->edge_arm = 0;
    return e;
}
static uint16_t h_adc(void *c, uint8_t ch) {
    sim_rig *r = (sim_rig *)c;
    switch (ch) {
    case ARM_ADC_TOOL_ID:
        if (r->tool_r_id_ohm < 0.0) return 4095;
        return (uint16_t)lround(r->tool_r_id_ohm / (ARM_TOOL_PULLUP_OHM + r->tool_r_id_ohm) * 4095.0);
    case ARM_ADC_TOOL_AUX1: return r->aux1_code;
    case ARM_ADC_VIN: return (uint16_t)lround((double)r->vin_mv / 11.0 / 3300.0 * 4095.0);
    default: return 0;
    }
}
static int h_ina(void *c, uint16_t *bus, int16_t *cur) {
    sim_rig *r = (sim_rig *)c;
    double ma = 0.0;
    unsigned i;
    if (r->ina_fail) return -1;
    if (powered(r) || r->rail_mv > 2000.0) {
        for (i = 1; i <= SIM_MAX_ID; ++i)
            if (r->sv[i].present && (i <= ARM_NUM_JOINTS || r->tool_en_pin))
                ma += r->sv[i].ram[STS_REG_MOVING] ? 400.0 : 120.0;
    }
    if (r->rail_mv > 2000.0) ma += r->extra_ma;
    *bus = (uint16_t)(((uint32_t)lround(r->rail_mv) / 4u) << 3);
    *cur = (int16_t)lround(ma * 4.0);
    return 0;
}
static void h_led(void *c, uint8_t rr, uint8_t g, uint8_t b) {
    sim_rig *r = (sim_rig *)c;
    r->led[0] = rr;
    r->led[1] = g;
    r->led[2] = b;
    ++r->led_changes;
}

static int h_wdt(void *c) { return ((sim_rig *)c)->watchdog_reset; }
static int h_cal_load(void *c, arm_cal *cal) {
    sim_rig *r = (sim_rig *)c;
    if (!r->cal_saved) return 0;
    *cal = r->saved_cal;
    return 1;
}
static int h_cal_save(void *c, const arm_cal *cal) {
    sim_rig *r = (sim_rig *)c;
    ++r->cal_saves;
    if (r->rail_mv > 2000.0) ++r->cal_saves_while_powered; /* flash writes must never overlap a live rail */
    r->saved_cal = *cal;
    r->cal_saved = 1;
    return 0;
}

void sim_rig_init(sim_rig *r) {
    unsigned i;
    memset(r, 0, sizeof *r);
    r->hw.ctx = r;
    r->hw.millis = h_millis;
    r->hw.bus_flush = h_bus_flush;
    r->hw.bus_write = h_bus_write;
    r->hw.bus_read = h_bus_read;
    r->hw.servo_en = h_servo_en;
    r->hw.tool_en = h_tool_en;
    r->hw.estop_sense = h_sense;
    r->hw.estop_take_edge = h_edge;
    r->hw.adc_read = h_adc;
    r->hw.ina_read = h_ina;
    r->hw.led = h_led;
    r->hw.watchdog_reset = h_wdt;
    r->hw.cal_load = h_cal_load;
    r->hw.cal_save = h_cal_save;
    r->vin_mv = 12000;
    r->tool_r_id_ohm = -1.0;
    r->fsr_base = 100;
    r->aux1_code = 100;
    for (i = 1; i <= SIM_MAX_ID; ++i) {
        sim_servo *s = &r->sv[i];
        s->present = i <= ARM_NUM_JOINTS ? 1u : 0u; /* tool servos appear with their tool */
        s->block_lo = -1e9;
        s->block_hi = 1e9;
        s->eeprom[STS_REG_RETURN_DELAY] = 250;
        wr16(s, STS_REG_MIN_ANGLE, 0);
        wr16(s, STS_REG_MAX_ANGLE, 4095);
        wr16(s, STS_REG_MAX_TORQUE, 1000);
        memcpy(s->eeprom, s->ram, 0);
        s->eeprom[STS_REG_RETURN_DELAY] = 250;
        s->eeprom[STS_REG_MIN_ANGLE] = 0;
        s->eeprom[STS_REG_MIN_ANGLE + 1u] = 0;
        s->eeprom[STS_REG_MAX_ANGLE] = 0xFF;
        s->eeprom[STS_REG_MAX_ANGLE + 1u] = 0x0F;
        s->eeprom[STS_REG_MAX_TORQUE] = 0xE8;
        s->eeprom[STS_REG_MAX_TORQUE + 1u] = 0x03;
        s->pos = 2048.0;
        s->speed_scale = 1.0;
        s->temp_c = 32;
        servo_reset_ram(s);
    }
}

void sim_rig_set_tool(sim_rig *r, double r_id_ohm) {
    unsigned i;
    r->tool_r_id_ohm = r_id_ohm;
    for (i = ARM_NUM_JOINTS + 1u; i <= SIM_MAX_ID; ++i) r->sv[i].present = 0;
    if (r_id_ohm < 0.0) return;
    for (i = 0; i < 4; ++i)
        if (fabs(kArmTools[i].r_id_ohm - r_id_ohm) < 1.0) {
            if (i < 3) {
                sim_servo *s = &r->sv[6u + i];
                s->present = 1;
                s->pos = i == 1 ? 0.0 : 1024.0; /* knob: step mode at 0; others at the closed stop */
            }
        }
}

void sim_rig_press_estop(sim_rig *r, int pressed) {
    if (pressed && !r->estop_pressed) {
        r->edge_arm = r->edge_bhms = 1;
        r->servo_en_pin = 0; /* the GPIO IRQ clears SERVO_EN at once */
        ++r->estop_cuts;
    }
    r->estop_pressed = pressed != 0;
}

void sim_rig_jam(sim_rig *r, unsigned id) {
    r->sv[id].block_lo = r->sv[id].block_hi = r->sv[id].pos;
}

void sim_rig_place(sim_rig *r, unsigned id, double raw) { r->sv[id].pos = raw; }
double sim_rig_pos(const sim_rig *r, unsigned id) { return r->sv[id].pos; }
uint16_t sim_rig_reg16(const sim_rig *r, unsigned id, unsigned addr) { return rg16(&r->sv[id], addr); }
uint8_t sim_rig_reg8(const sim_rig *r, unsigned id, unsigned addr) { return r->sv[id].ram[addr]; }

void sim_rig_advance(sim_rig *r, uint32_t ms) {
    uint32_t k;
    unsigned i;
    for (k = 0; k < ms; ++k) {
        double target = 0.0;
        ++r->now_ms;
        /* Q2 conducts while contact A is closed (or welded) and SERVO_EN is high. */
        if (r->servo_en_pin && (!r->estop_pressed || r->contact_a_welded) && r->vin_mv >= 9000u)
            target = (double)r->vin_mv;
        if (r->contact_a_welded && r->servo_en_pin == 0 && !r->estop_pressed) target = 0.0;
        if (r->contact_a_welded && r->estop_pressed) target = (double)r->vin_mv; /* contact stuck closed */
        if (r->rail_mv < target) r->rail_mv = fmin(target, r->rail_mv + 2400.0);
        else if (r->rail_mv > target) r->rail_mv = fmax(target, r->rail_mv - 4000.0);
        for (i = 1; i <= SIM_MAX_ID; ++i) {
            if (i > ARM_NUM_JOINTS && !r->tool_en_pin) { /* tool servos need V_TOOL too */
                if (r->sv[i].was_powered) { servo_reset_ram(&r->sv[i]); r->sv[i].was_powered = 0; }
                continue;
            }
            servo_tick(r, &r->sv[i]);
        }
    }
}
