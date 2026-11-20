/* Native-only access to one private accounting phase. This translation unit
 * replaces standalone standing.c only in differential control builds. It
 * exposes no firmware API and is never part of the AVR image. */
#if defined(HMS_EQ_BASELINE)
#include "../../originals/project/protocol/endpoint/standing.c"
#else
#include "../protocol/endpoint/standing.c"
#endif

uint8_t hms_phase_test_account(hms_standing *s,uint8_t commit,uint64_t until) {
    return account_ok(s,commit,until);
}
