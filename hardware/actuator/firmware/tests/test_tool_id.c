/* Tool-ID decoding (window table of INTERFACE.md section 5) and debouncing. */
#include <math.h>

#include "arm_params.h"
#include "bhms_test.h"
#include "tool_id.h"

static uint16_t code_for(double r_id) { return (uint16_t)lround(r_id / (ARM_TOOL_PULLUP_OHM + r_id) * 4095.0); }

static void test_decode_windows(void) {
    unsigned i;
    double tol;
    /* Every nominal R_ID decodes to its own code, also at +-1 % resistor tolerance (the
     * windows leave far more room than that). */
    for (i = 0; i < 8; ++i)
        for (tol = 0.99; tol < 1.011; tol += 0.01) {
            uint16_t c = code_for(kArmTools[i].r_id_ohm * tol);
            CHECK(tool_id_decode(c) == kArmTools[i].code);
        }
    CHECK(tool_id_decode(0) == ARM_TOOL_FAULT);      /* short to GND */
    CHECK(tool_id_decode(100) == ARM_TOOL_FAULT);
    CHECK(tool_id_decode(4095) == ARM_TOOL_NONE);    /* open: pulled up */
    CHECK(tool_id_decode(4000) == ARM_TOOL_NONE);
    CHECK(tool_id_decode(60000) == ARM_TOOL_NONE);   /* out-of-range ADC value is clamped */
    /* Window edges from the table: 0.129 and 0.207 of full scale. */
    CHECK(tool_id_decode((uint16_t)(0.128 * 4095)) == 1 && tool_id_decode((uint16_t)(0.131 * 4095)) == 5);
    CHECK(tool_id_decode((uint16_t)(0.205 * 4095)) == 5 && tool_id_decode((uint16_t)(0.209 * 4095)) == 2);
}

static void test_debounce(void) {
    tool_id_filter f;
    uint32_t t = 100;
    unsigned k;
    uint16_t grip = code_for(1000), knob = code_for(3300);
    tool_id_init(&f);
    CHECK(f.stable == ARM_TOOL_NONE);
    /* Needs 5 consecutive matching samples, 10 ms apart. */
    for (k = 0; k < 4; ++k) {
        CHECK(!tool_id_update(&f, t, grip));
        t += 10;
    }
    CHECK(f.stable == ARM_TOOL_NONE);
    CHECK(tool_id_update(&f, t, grip) && f.stable == ARM_TOOL_GRIPPER);
    t += 10;
    /* Samples closer than 10 ms apart are ignored. */
    CHECK(!tool_id_update(&f, t - 7, knob) && f.run == 5);
    /* A glitch inside a stable run does not change the identity. */
    CHECK(!tool_id_update(&f, t, knob));
    t += 10;
    CHECK(!tool_id_update(&f, t, grip) && f.stable == ARM_TOOL_GRIPPER);
    t += 10;
    /* A different tool needs its own 5 samples. */
    for (k = 0; k < 4; ++k) {
        CHECK(!tool_id_update(&f, t, knob));
        t += 10;
    }
    CHECK(tool_id_update(&f, t, knob) && f.stable == ARM_TOOL_KNOB_TURNER);
    t += 10;
    /* Hot unplug (open circuit) is reported at the first sample. */
    CHECK(tool_id_update(&f, t, 4095) && f.stable == ARM_TOOL_NONE);
    /* A shorted ID pin is a fault class, stable after 5 samples. */
    for (k = 0; k < 5; ++k) {
        t += 10;
        (void)tool_id_update(&f, t, 0);
    }
    CHECK(f.stable == ARM_TOOL_FAULT);
}

int main(void) {
    test_decode_windows();
    test_debounce();
    TEST_FINISH("test_tool_id");
}
