#ifndef HMS_STANDING_H
#define HMS_STANDING_H
#include "endpoint.h"

/* Canonical fixed-storage byte arrays, never native structs on the wire.
 * All pointers/configuration plus endpoint attachment are charged to the32B
 * AVR glue ceiling. The arena replaces the already reserved256B allowance. */
enum hms_st_offset {
    ST_HIGH=0, ST_SLOT=4, ST_REV=5, ST_MUT=9, ST_BODY=13, ST_LEASE=33,
    ST_ACT=41, ST_ACK=45, ST_NEXT=49, ST_LOSS_AT=57, ST_CLEANUP=65,
    ST_QUIET_AT=73, ST_EPOCH=81, ST_ACCOUNT=89, ST_LIFE=93,
    ST_TARGET=94, ST_PHASE=95, ST_OWNED=96, ST_QUIET=97, ST_REASON=98,
    ST_FLAGS=100, ST_HEAD=102, ST_COUNT=103, ST_PENDING=104,
    ST_LOSS_COMMAND=105, ST_WITNESS=106
};
enum hms_st_life { ST_NONE, ST_PREPARED, ST_ACTIVE, ST_DRAINING,
    ST_SUSPENDED, ST_STOPPED, ST_FAULT };
enum hms_st_slot { ST_EMPTY, ST_FINITE, ST_STANDING };
enum hms_st_reason { ST_NO_REASON, ST_STOP, ST_SUSPEND, ST_LEASE_LOSS,
    ST_LEDGER, ST_STALE, ST_QUALITY, ST_EPOCH_LOSS, ST_GAP,
    ST_FEEDBACK, ST_GUARD, ST_AUTHORITY, ST_CLOCK, ST_DRIVER,
    ST_COUNTER, ST_ACCOUNT_LOSS, ST_TIMING };
enum hms_st_flags { ST_EVER=1u, ST_UNRESOLVED=2u, ST_DISPUTED=4u,
    ST_STARTED=8u, ST_RESUMED=16u, ST_DEMAND_READY=32u,
    ST_FEEDBACK_READY=64u, ST_WITNESS_VALID=128u, ST_LOSS=256u,
    ST_LOSS_POSSIBLE=512u, ST_EXHAUSTED=1024u,
    ST_DEMAND_FAULT=2048u, ST_FEEDBACK_FAULT=4096u };
enum hms_st_status { ST_BAD_REVISION=23, ST_ACK_PENDING=24,
    ST_BAD_PAGE=25, ST_SOURCE_INVALID=26 };
enum hms_st_opcode { ST_DESCRIBE=1, ST_BIND=16, ST_REVOKE=18,
    ST_OPEN=64, ST_START=65, ST_RENEW=66, ST_STATUS=67, ST_ACKNOWLEDGE=68,
    ST_SUSPEND_OP=69, ST_RESUME=70, ST_STOP_OP=71, ST_RETIRE=72 };
enum hms_st_driver_phase { ST_ACQUIRE_DEMAND, ST_ACQUIRE_FEEDBACK,
    ST_SET_OUTPUT, ST_LOSS_OUTPUT, ST_LOSS_OBSERVE };
enum hms_st_report_kind { ST_REPORT_NONE, ST_REPORT_SAMPLE,
    ST_REPORT_DISPATCH, ST_REPORT_QUIET };
enum hms_st_record_state { ST_RECORD_PENDING=1, ST_RECORD_SUCCESS,
    ST_RECORD_FAILED, ST_RECORD_INTERRUPTED, ST_RECORD_UNKNOWN };

/* report32: kind0,channel1,quality2,evidence3,verification4,continuity5,
 * command6,effect7 (bit0 possible,bit1 accepted,bit2 precise dispatch time),
 * aggregate quiescent mask8,reserved9..11,epoch12,sequence16,tick20,value28.
 * Report arrays are callback-local. Drivers enforce cutoff at the actual I/O
 * boundary. No callback may reenter or mutate endpoint/controller storage. */
typedef struct {
    void *user;
    uint32_t (*source_epoch)(void *user, uint8_t channel);
    uint8_t (*guard)(void *user, const uint8_t configuration[32], uint8_t initial_baseline);
    void (*step)(void *user, const struct hms_standing *authority,
                 uint8_t phase, uint8_t command, uint64_t now,
                 uint64_t exclusive_cutoff, uint8_t report[32]);
    uint32_t max_on_ms;
    uint16_t cleanup_ms;
    uint8_t resource_mask;
} hms_st_config;
typedef struct {
    uint8_t driver[64], configuration[32], work[24];
    uint8_t observation[2][24], record[2][44];
} hms_st_arena;
typedef struct hms_standing {
    uint8_t bytes[128];
    hms_endpoint *endpoint;
    const hms_st_config *config;
    hms_st_arena *arena;
} hms_standing;

/* Attach once in an initialized empty fresh-boot endpoint, before any work.
 * Driver bytes belong to the installed implementation and are not cleared. */
uint8_t hms_standing_attach(hms_standing *, hms_endpoint *,
                           const hms_st_config *, hms_st_arena *);
uint8_t hms_standing_handle(hms_standing *, uint8_t kind, uint8_t channel,
    uint64_t session, uint32_t sequence, const uint8_t *, uint16_t,
    uint64_t now, uint16_t flags, uint8_t *response, uint16_t *length);
void hms_standing_poll(hms_standing *);
void hms_standing_finite_slot(hms_standing *, uint8_t occupied);

/* Candidate common-core hooks; these preserve the original trusted platform
 * and context authority. They never provide another resource lock table. */
void hms_endpoint_refresh(hms_endpoint *, uint64_t, uint16_t);
void hms_endpoint_fresh_clock(hms_endpoint *);
uint8_t hms_endpoint_readiness(const hms_endpoint *);
uint8_t hms_endpoint_bind_shared(hms_endpoint *, const uint8_t *);
uint8_t hms_endpoint_revoke_shared(hms_endpoint *, const uint8_t *);
void hms_endpoint_counter_fault(hms_endpoint *);
#endif
