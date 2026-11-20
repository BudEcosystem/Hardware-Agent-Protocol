#ifndef HMS_ENDPOINT_LINK_H
#define HMS_ENDPOINT_LINK_H
#include "endpoint.h"
#include "../serial/frame.h"

typedef struct {
    hms_frame_parser parser;
    uint8_t transmit[HMS_FRAME_RAW];
    uint16_t transmit_length, transmit_index;
    uint8_t transmit_phase, escape_pending;
    uint64_t receive_started;
    uint32_t receive_budget_ms;
    uint8_t receive_partial;
} hms_endpoint_link;

void hms_endpoint_link_init(hms_endpoint_link *link);
/* Only the partial parser resets. Endpoint slots/epochs/fences do not. */
void hms_endpoint_link_reset_receive(hms_endpoint_link *link);
/* Default synthetic budget is 1000 ms, not a qualified UART timing claim.
 * Configure while inhibited; changing budget discards the partial frame. */
uint8_t hms_endpoint_link_set_receive_budget(hms_endpoint_link *link, uint32_t milliseconds);
/* Call even without incoming bytes; requires a qualified timer or a platform
 * error/reset path when that timer is unavailable. No endpoint state reset. */
void hms_endpoint_link_check_deadline(hms_endpoint_link *link, uint64_t now_tick);
/* Internal transport join: before_feed precedes exactly one parser feed.
 * accept_ready is called exactly once only after that feed returned READY and
 * the transport established continuity. One owner; consume raw synchronously.
 * These do not validate a caller-invented READY or expose an alternate wire. */
void hms_endpoint_link_before_feed(hms_endpoint_link *link, uint8_t byte, uint64_t now_tick);
void hms_endpoint_link_accept_ready(hms_endpoint_link *link, hms_endpoint *endpoint,
                                    uint64_t now_tick, uint16_t platform_flags);
/* One input byte, bounded work. Caller supplies qualified clock/flags.
 * Under TX backpressure only v1 CANCEL/REVOKE and v2 STOP/SUSPEND/REVOKE are processed, their replies may
 * be dropped; other frames are dropped before admission. One pending frame,
 * no queue and no partial-frame replacement. */
void hms_endpoint_link_feed(hms_endpoint_link *link, hms_endpoint *endpoint,
                            uint8_t byte, uint64_t now_tick, uint16_t platform_flags);
/* Produce one escaped wire byte without blocking. 0 means idle. */
uint8_t hms_endpoint_link_next(hms_endpoint_link *link, uint8_t *byte);
#endif
