#ifndef HMS_STANDING_FIXTURE_H
#define HMS_STANDING_FIXTURE_H
#include "../protocol/endpoint/standing.h"

/* The complete synthetic finite+standing driver state is exactly64 bytes,
 * owned by arena.driver. No hidden target globals or physical evidence. */
enum hms_st_fixture_offset {
    FX_CLOCK=0, FX_FLAGS=8, FX_OUTPUT=10, FX_DENY=11,
    FX_EPOCH=12, FX_SEQUENCE=20, FX_DEMAND=28, FX_FEEDBACK=32,
    FX_DISPATCHES=36, FX_LOSSES=40, FX_STEP_ADVANCE=44,
    FX_GUARD_ADVANCE=48, FX_INJECT=52, FX_FINITE_ACTIVE=53, FX_BOUNDARY_DRIFT=54,
    FX_WITNESS_TIME=55, FX_FINITE_STARTED=56, FX_LAST_LOSS_HANDOFF=56
};
enum hms_st_fixture_injection { FX_BAD_QUALITY=1, FX_BAD_EPOCH=2,
    FX_DUPLICATE=4, FX_FALSE_PHYSICAL=8, FX_LATE=16,
    FX_IGNORE_CUTOFF=32, FX_NO_QUIET=64, FX_CLOCK_LOSS=128 };
uint32_t hms_st_fixture_read32(const uint8_t *);
uint64_t hms_st_fixture_read64(const uint8_t *);
void hms_st_fixture_write32(uint8_t *,uint32_t);
void hms_st_fixture_write64(uint8_t *,uint64_t);
void hms_st_fixture_init(hms_st_arena *,hms_ep_config *,hms_st_config *);
#endif
