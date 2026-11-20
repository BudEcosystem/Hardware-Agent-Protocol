#include "endpoint_kernel.h"
#include <string.h>

uint32_t hms_ep_read32(const uint8_t *p) {
    uint32_t value=0;uint8_t i;
    for(i=0;i<4u;++i)value=(value<<8)|p[i];
    return value;
}
uint64_t hms_ep_read64(const uint8_t *p) {
    uint64_t value=0;uint8_t i;
    for(i=0;i<8u;++i)value=(value<<8)|p[i];
    return value;
}
static void write16(uint8_t *p,uint16_t value) {
    p[0]=(uint8_t)(value>>8);p[1]=(uint8_t)value;
}
void hms_ep_write32(uint8_t *p,uint32_t value) {
    uint8_t i;for(i=0;i<4u;++i){p[3u-i]=(uint8_t)value;value>>=8;}
}
void hms_ep_write64(uint8_t *p,uint64_t value) {
    uint8_t i;for(i=0;i<8u;++i){p[7u-i]=(uint8_t)value;value>>=8;}
}
void hms_ep_write64_snapshot(uint8_t *p,const uint64_t *source) {
    uint64_t value=*source;hms_ep_write64(p,value);
}
void hms_ep_write64_sum(uint8_t *p,const uint64_t *source,uint32_t delta) {
    uint64_t value=*source+delta;hms_ep_write64(p,value);
}
void hms_ep_write64_encoded_sum(uint8_t *p,const uint8_t *source,uint32_t delta) {
    uint64_t value=hms_ep_read64(source)+delta;hms_ep_write64(p,value);
}
void hms_ep_write_context(uint8_t *p,const hms_endpoint *e) {
    /* Keep individual reads/stores in order, including if p aliases e. */
    hms_ep_write32(p,e->control_generation);write16(p+4,e->context_handle);
    memcpy(p+6,e->context_digest,32);
}
void hms_ep_write_finite_tail(uint8_t *p,const hms_endpoint *e) {
    hms_ep_write64_snapshot(p,&e->now_tick);
    hms_ep_write64_snapshot(p+8,&e->armed_until);
    hms_ep_write32(p+16,e->call_high_water);p[20]=e->receipt.held_mask;
}
void hms_ep_commit_observation(uint8_t *o,const uint8_t *report) {
    memcpy(o,report+28,4);memcpy(o+4,report+20,8);memcpy(o+12,report+16,4);
    memcpy(o+16,report+12,4);o[20]=1;o[21]=1;o[22]=1;o[23]=0;
}
static int8_t compare(uint64_t left,uint64_t right) {
    if(left<right)return -1;
    return (int8_t)(left>right);
}
int8_t hms_ep_time_cmp(const uint64_t *left,const uint64_t *right) {
    return compare(*left,*right);
}
int8_t hms_ep_time_cmp_encoded(const uint64_t *left,const uint8_t *right) {
    return compare(*left,hms_ep_read64(right));
}
int8_t hms_ep_elapsed_cmp(const uint64_t *end,const uint64_t *start,uint32_t bound) {
    return compare(*end-*start,bound);
}
int8_t hms_ep_elapsed_cmp_encoded(const uint64_t *end,const uint8_t *start,uint32_t bound) {
    return compare(*end-hms_ep_read64(start),bound);
}
int8_t hms_ep_elapsed_encoded_cmp(const uint8_t *end,const uint8_t *start,uint32_t bound) {
    return compare(hms_ep_read64(end)-hms_ep_read64(start),bound);
}
int8_t hms_ep_add_room_cmp(const uint64_t *value,uint32_t delta) {
    return compare(*value,UINT64_MAX-delta);
}
void hms_ep_cutoff_min(uint64_t *cutoff,const uint8_t *base,uint32_t delta) {
    uint64_t at=hms_ep_read64(base);
    uint64_t candidate=at<UINT64_MAX-delta?at+delta:UINT64_MAX;
    if(candidate<*cutoff)*cutoff=candidate;
}
void hms_ep_write_age(uint8_t *p,const uint64_t *end,const uint8_t *start) {
    uint16_t value=(uint16_t)(*end-hms_ep_read64(start));write16(p,value);
}
void hms_ep_write_encoded_age(uint8_t *p,const uint8_t *end,const uint8_t *start) {
    uint16_t value=(uint16_t)(hms_ep_read64(end)-hms_ep_read64(start));write16(p,value);
}
