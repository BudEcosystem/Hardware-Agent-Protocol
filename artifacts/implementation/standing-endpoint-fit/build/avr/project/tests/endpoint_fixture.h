#ifndef HMS_ENDPOINT_FIXTURE_H
#define HMS_ENDPOINT_FIXTURE_H
#include "../protocol/endpoint/endpoint.h"

enum hms_fixture_mode { HMS_FIXTURE_NORMAL, HMS_FIXTURE_COMPLETE_ON_CANCEL,
    HMS_FIXTURE_REJECT_CANCEL, HMS_FIXTURE_NO_QUIESCENCE,
    HMS_FIXTURE_FALSE_PHYSICAL, HMS_FIXTURE_OVERSIZE_RESULT,
    HMS_FIXTURE_NEVER_COMPLETE, HMS_FIXTURE_EARLY_QUIESCENCE,
    HMS_FIXTURE_LATE_CALLBACK };
typedef struct {
    uint64_t started, clock_tick;
    uint32_t dispatches, effects, loss_steps, cancel_steps;
    uint32_t guard_advance_ms, step_advance_ms;
    int32_t sum;
    uint16_t platform_flags;
    uint8_t active, pending_quiescence, mode, guard_denied;
#ifndef __AVR__
    uint8_t constants[80];
#endif
} hms_endpoint_fixture;

void hms_endpoint_fixture_init(hms_endpoint_fixture *fixture, hms_ep_config *config);
#ifndef __AVR__
uint8_t hms_endpoint_fixture_constant(hms_endpoint_fixture *fixture, uint8_t which, const char *hex);
#endif
#endif
