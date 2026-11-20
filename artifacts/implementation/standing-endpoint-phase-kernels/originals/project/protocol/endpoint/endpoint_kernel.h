#ifndef HMS_ENDPOINT_KERNEL_H
#define HMS_ENDPOINT_KERNEL_H
#include "endpoint.h"

/* Private implementation leaves, not protocol/driver ABI. The selected GCC
 * profile requires sharing; generated code must still check clones/frames.
 * Other compilers remain source-compatible, without a qualified size bound. */
#if defined(__GNUC__)
#define HMS_EP_SHARED __attribute__((noinline))
#else
#define HMS_EP_SHARED
#endif

uint32_t HMS_EP_SHARED hms_ep_read32(const uint8_t *);
uint64_t HMS_EP_SHARED hms_ep_read64(const uint8_t *);
void HMS_EP_SHARED hms_ep_write32(uint8_t *,uint32_t);
void HMS_EP_SHARED hms_ep_write64(uint8_t *,uint64_t);
void HMS_EP_SHARED hms_ep_write64_snapshot(uint8_t *,const uint64_t *);
void HMS_EP_SHARED hms_ep_write64_sum(uint8_t *,const uint64_t *,uint32_t);
void HMS_EP_SHARED hms_ep_write64_encoded_sum(uint8_t *,const uint8_t *,uint32_t);
void HMS_EP_SHARED hms_ep_write_context(uint8_t *,const hms_endpoint *);
void HMS_EP_SHARED hms_ep_write_finite_tail(uint8_t *,const hms_endpoint *);
void HMS_EP_SHARED hms_ep_commit_observation(uint8_t *,const uint8_t *);

/* Three-way unsigned comparisons; ABSENT and ordering policy stay at callers.
 * Differences are modulo2^64 exactly, even when end<start. No callbacks/state
 * writes occur in these leaves. uint32 bounds do not narrow timestamp values. */
int8_t HMS_EP_SHARED hms_ep_time_cmp(const uint64_t *,const uint64_t *);
int8_t HMS_EP_SHARED hms_ep_time_cmp_encoded(const uint64_t *,const uint8_t *);
int8_t HMS_EP_SHARED hms_ep_elapsed_cmp(const uint64_t *,const uint64_t *,uint32_t);
int8_t HMS_EP_SHARED hms_ep_elapsed_cmp_encoded(const uint64_t *,const uint8_t *,uint32_t);
int8_t HMS_EP_SHARED hms_ep_elapsed_encoded_cmp(const uint8_t *,const uint8_t *,uint32_t);
int8_t HMS_EP_SHARED hms_ep_add_room_cmp(const uint64_t *,uint32_t);
void HMS_EP_SHARED hms_ep_cutoff_min(uint64_t *,const uint8_t *,uint32_t);
void HMS_EP_SHARED hms_ep_write_age(uint8_t *,const uint64_t *,const uint8_t *);
void HMS_EP_SHARED hms_ep_write_encoded_age(uint8_t *,const uint8_t *,const uint8_t *);
#endif
