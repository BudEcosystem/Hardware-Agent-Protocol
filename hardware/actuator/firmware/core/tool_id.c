#include "tool_id.h"

#include <string.h>

#include "arm_params.h"

/* Window upper bounds as ratios of full scale (INTERFACE.md section 5 table). */
static const float kBound[9] = {0.045f, 0.129f, 0.207f, 0.304f, 0.430f, 0.571f, 0.705f, 0.838f, 0.955f};
/* Codes of the windows in order: short, then R_ID 1k, 2k, 3.3k, 5.6k, 10k, 18k, 33k, 100k. */
static const uint8_t kCode[10] = {ARM_TOOL_FAULT, 1, 5, 2, 6, 3, 7, 4, 8, ARM_TOOL_NONE};

uint8_t tool_id_decode(uint16_t adc12) {
    float ratio = (float)(adc12 > 4095u ? 4095u : adc12) / 4095.0f;
    unsigned i;
    for (i = 0; i < 9u; ++i)
        if (ratio < kBound[i]) return kCode[i];
    return kCode[9];
}

void tool_id_init(tool_id_filter *f) {
    memset(f, 0, sizeof *f);
    f->stable = ARM_TOOL_NONE;
    f->candidate = ARM_TOOL_NONE;
}

int tool_id_update(tool_id_filter *f, uint32_t now_ms, uint16_t adc12) {
    uint8_t id;
    if (f->primed && (uint32_t)(now_ms - f->last_ms) < TOOL_ID_SAMPLE_MS) return 0;
    f->primed = 1;
    f->last_ms = now_ms;
    id = tool_id_decode(adc12);
    if (id == f->candidate) {
        if (f->run < 255u) ++f->run;
    } else {
        f->candidate = id;
        f->run = 1;
    }
    if (id == ARM_TOOL_NONE && f->stable != ARM_TOOL_NONE) {
        f->stable = ARM_TOOL_NONE; /* hot unplug: immediate */
        return 1;
    }
    if (f->run >= TOOL_ID_STABLE_SAMPLES && f->stable != id) {
        f->stable = id;
        return 1;
    }
    return 0;
}
