#ifndef HMS_ENDPOINT_SCENARIO_FIXTURE_H
#define HMS_ENDPOINT_SCENARIO_FIXTURE_H
#include "endpoint.h"

/* Original installed synthetic primitives, never physical device drivers. */
enum hms_scenario_mode { HMS_SCENARIO_NORMAL, HMS_SCENARIO_COMPLETE_ON_CANCEL,
    HMS_SCENARIO_REJECT_CANCEL, HMS_SCENARIO_NO_QUIESCENCE,
    HMS_SCENARIO_FALSE_PHYSICAL, HMS_SCENARIO_OVERSIZE_RESULT,
    HMS_SCENARIO_NEVER_COMPLETE, HMS_SCENARIO_EARLY_QUIESCENCE,
    HMS_SCENARIO_LATE_CALLBACK };
typedef struct {
    uint64_t started, clock_tick;
    uint64_t sample_ticks[3];
    uint32_t values[3], dispatches, effects, loss_steps, cancel_steps;
    uint16_t platform_flags;
    uint8_t active, pending_quiescence, mode, guard_denied;
    /* Optional platform clock override; NULL selects explicit synthetic tick. */
    uint8_t (*clock_snapshot)(void *user, uint64_t *tick, uint16_t *flags);
    uint8_t constants[80];
} hms_scenario_fixture;

void hms_scenario_fixture_init(hms_scenario_fixture *fixture, hms_ep_config *config);
uint8_t hms_scenario_fixture_constant(hms_scenario_fixture *fixture, uint8_t which, const char *hex);
#endif
