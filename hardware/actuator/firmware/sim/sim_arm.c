/* Host build of the BHMS Arm firmware: the real endpoint and arm logic (core/) on stdin/stdout
 * (a pty), running against the simulated rig. Tests/test_e2e.py drives it with the Task 9a
 * Python harness; a SimLab adapter can attach to the same process through the control FIFO.
 *
 *   sim_arm [--epoch FILE] [--ctl FIFO] [--tool OHMS] [--vin MV] [--uncalibrated 1]
 * By default the arm starts calibrated (nominal zero); --uncalibrated boots with no stored calibration
 * and the arm resting at the rest pose, so the `calibrate` action can be exercised.
 *
 * Control FIFO lines (the hardware the host cannot touch):
 *   estop 0|1    press / release the E-stop      tool OHMS|none   fit / remove a tool
 *   vin MV       supply voltage                  weld 0|1         contact A welded (rail stays)
 *   object RAW   a gripper object stops the fingers at RAW      fsr   enable the FSR contact model
 * State changes are reported on stderr: "STATE n", "SERVO_EN 0|1", "TOOL_EN 0|1", "POS id raw". */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "arm_device.h"
#include "bhms_hal_posix.h"
#include "sim_rig.h"

static sim_rig g_rig;
static int g_fsr;

static uint32_t sim_millis(void *c) { (void)c; return g_rig.now_ms; }
static int sim_stop_pin(void *c) {
    int v = g_rig.estop_pressed || g_rig.edge_bhms;
    (void)c;
    g_rig.edge_bhms = 0; /* the latch is read once, as the HAL contract requires */
    return v;
}

static void ctl_line(char *line) {
    int v;
    double d;
    unsigned u;
    if (sscanf(line, "estop %d", &v) == 1) sim_rig_press_estop(&g_rig, v);
    else if (sscanf(line, "vin %u", &u) == 1) g_rig.vin_mv = u;
    else if (sscanf(line, "weld %d", &v) == 1) g_rig.contact_a_welded = v;
    else if (sscanf(line, "object %lf", &d) == 1) g_rig.sv[6].block_lo = d;
    else if (strncmp(line, "tool none", 9) == 0) sim_rig_set_tool(&g_rig, -1.0);
    else if (sscanf(line, "tool %lf", &d) == 1) sim_rig_set_tool(&g_rig, d);
    else if (strncmp(line, "fsr", 3) == 0) {
        g_fsr = 1;
        g_rig.sv[8].block_hi = 1883.0 + 400.0;
    }
}

static void ctl_poll(int fd) {
    static char buf[128];
    static size_t n;
    char c;
    while (fd >= 0 && read(fd, &c, 1) == 1) {
        if (c == '\n' || n + 1 >= sizeof buf) {
            buf[n] = 0;
            ctl_line(buf);
            n = 0;
        } else {
            buf[n++] = c;
        }
    }
}

int main(int argc, char **argv) {
    const char *epoch_path = NULL, *ctl_path = NULL;
    double tool = -1.0;
    unsigned vin = 12000;
    int uncalibrated = 0;
    arm_cal nominal;
    int ctl = -1, i;
    bhms_posix px;
    bhms_hal hal;
    arm a;
    arm_device dev;
    struct timespec t0, now;
    uint32_t last_state = 255, last_en = 2, last_tool_en = 2;
    for (i = 1; i + 1 < argc; i += 2) {
        if (strcmp(argv[i], "--epoch") == 0) epoch_path = argv[i + 1];
        else if (strcmp(argv[i], "--ctl") == 0) ctl_path = argv[i + 1];
        else if (strcmp(argv[i], "--tool") == 0) tool = atof(argv[i + 1]);
        else if (strcmp(argv[i], "--vin") == 0) vin = (unsigned)atoi(argv[i + 1]);
        else if (strcmp(argv[i], "--uncalibrated") == 0) uncalibrated = atoi(argv[i + 1]);
        else return 2;
    }
    if (ctl_path != NULL) ctl = open(ctl_path, O_RDWR | O_NONBLOCK);
    sim_rig_init(&g_rig);
    g_rig.vin_mv = vin;
    if (tool > 0.0) sim_rig_set_tool(&g_rig, tool);
    bhms_posix_init(&px, 0, 1, epoch_path);
    hal = px.hal;
    hal.millis = sim_millis;
    hal.stop_pin = sim_stop_pin;
    arm_cal_nominal(&nominal);
    if (uncalibrated) {
        for (i = 0; i < (int)ARM_NUM_JOINTS; ++i) {
            int32_t raw;
            if (arm_to_raw(&nominal, (unsigned)i, kArmRestPose[i], &raw) == 0)
                sim_rig_place(&g_rig, (unsigned)i + 1u, (double)raw);
        }
    }
    arm_init(&a, &g_rig.hw, uncalibrated ? 0 : &nominal, 0);
    if (arm_device_init(&dev, &a, &hal) != BHMS_OK) return 3;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (;;) {
        uint64_t real_ms;
        (void)bhms_posix_wait(&px, 1);
        ctl_poll(ctl);
        clock_gettime(CLOCK_MONOTONIC, &now);
        real_ms = (uint64_t)(now.tv_sec - t0.tv_sec) * 1000u + (uint64_t)((now.tv_nsec - t0.tv_nsec) / 1000000);
        do {
            if (g_rig.now_ms < real_ms) sim_rig_advance(&g_rig, 1);
            if (g_fsr) {
                double over = sim_rig_pos(&g_rig, 8) - 1883.0;
                g_rig.aux1_code = (uint16_t)(100.0 + (over > 0.0 ? over * 8.0 : 0.0));
            }
            arm_device_poll(&dev);
        } while (g_rig.now_ms < real_ms);
        if ((uint32_t)a.state != last_state) {
            last_state = (uint32_t)a.state;
            fprintf(stderr, "STATE %u\n", (unsigned)last_state);
            fflush(stderr);
        }
        if ((uint32_t)g_rig.servo_en_pin != last_en) {
            last_en = (uint32_t)g_rig.servo_en_pin;
            fprintf(stderr, "SERVO_EN %u\n", (unsigned)last_en);
            fflush(stderr);
        }
        if ((uint32_t)g_rig.tool_en_pin != last_tool_en) {
            last_tool_en = (uint32_t)g_rig.tool_en_pin;
            fprintf(stderr, "TOOL_EN %u\n", (unsigned)last_tool_en);
            fflush(stderr);
        }
    }
}
