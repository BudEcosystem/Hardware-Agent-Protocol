/* Tool identity from the TOOL_ID divider (INTERFACE.md section 5): ratio = code / 4095 =
 * R_ID / (10 k + R_ID), decoded by window and accepted only after 5 consecutive matching
 * samples taken 10 ms apart.
 * Thread-safety: single owner. */
#ifndef ARM_TOOL_ID_H
#define ARM_TOOL_ID_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TOOL_ID_SAMPLE_MS 10u
#define TOOL_ID_STABLE_SAMPLES 5u

/* Decode one 12-bit reading: 1..8 (tool code; 5..8 reserved), ARM_TOOL_NONE (open circuit)
 * or ARM_TOOL_FAULT (short, or a value between windows is reported as the nearest window
 * boundary class: the windows tile the whole range, so every code decodes). */
uint8_t tool_id_decode(uint16_t adc12);

typedef struct {
    uint8_t stable;     /* last accepted id (ARM_TOOL_NONE until the first stable run) */
    uint8_t candidate;
    uint8_t run;        /* consecutive samples equal to candidate */
    uint8_t primed;
    uint32_t last_ms;
} tool_id_filter;

void tool_id_init(tool_id_filter *f);
/* Feed one sample if TOOL_ID_SAMPLE_MS elapsed since the previous one. Returns nonzero when
 * `stable` changed on this call. A change to ARM_TOOL_NONE is accepted after a single sample
 * so a knocked-off tool is reported at once (INTERFACE.md "Hot unplug"). */
int tool_id_update(tool_id_filter *f, uint32_t now_ms, uint16_t adc12);

#ifdef __cplusplus
}
#endif
#endif
