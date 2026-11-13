/* BHMS-Compact build-time bounds. Override with -D before including bhms.h.
 * Every buffer in the library is sized from these; there is no heap. */
#ifndef BHMS_CONFIG_H
#define BHMS_CONFIG_H

/* Replay ring entries (BHMS-CMP-031 requires >= 4). */
#ifndef BHMS_RING_SIZE
#define BHMS_RING_SIZE 4u
#endif
/* Concurrently active operations reported in HELLO (1..BHMS_RING_SIZE). */
#ifndef BHMS_MAX_ACTIVE
#define BHMS_MAX_ACTIVE 2u
#endif
/* Largest INVOKE argument block / RESULT field block, in wire bytes (<= 182). */
#ifndef BHMS_MAX_ARGS
#define BHMS_MAX_ARGS 16u
#endif
#ifndef BHMS_MAX_RESULT
#define BHMS_MAX_RESULT 16u
#endif
/* Largest field count of one action layout. */
#ifndef BHMS_MAX_FIELDS
#define BHMS_MAX_FIELDS 8u
#endif
/* Absolute receive deadline for one frame (ms). A partial frame older than
 * this is discarded (the framing parser leaves the deadline to the caller). */
#ifndef BHMS_RX_TIMEOUT_MS
#define BHMS_RX_TIMEOUT_MS 250u
#endif
/* Bytes consumed from the UART per bhms_poll call; bounds one poll's work. */
#ifndef BHMS_POLL_MAX_BYTES
#define BHMS_POLL_MAX_BYTES 128u
#endif

#endif
