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
/* Operand format is only a byte-index flip (0 native little endian, 7
 * encoded/native big endian). Fixed entry points select it; this is not an
 * operation descriptor/interpreter and allocates no descriptor or table. */
#if HMS_EP_BYTE_BACKEND
_Static_assert(sizeof(uint64_t)==8u,"byte backend exact uint64 object");
#define NATIVE_PAIR ((uint8_t)(HMS_EP_NATIVE_FLIP|(HMS_EP_NATIVE_FLIP<<4)))
#define NATIVE_ENCODED ((uint8_t)(HMS_EP_NATIVE_FLIP|0x70u))
#define ENCODED_NATIVE ((uint8_t)(7u|(HMS_EP_NATIVE_FLIP<<4)))
static int8_t byte_compare(const unsigned char *a,const unsigned char *b,uint8_t flips) {
    uint8_t i=8,a_flip=(uint8_t)(flips&7u),b_flip=(uint8_t)(flips>>4);
    while(i!=0u){uint8_t left,right;--i;left=a[i^a_flip];right=b[i^b_flip];
        if(left!=right)return (int8_t)(left<right?-1:1);}
    return 0;
}
static int8_t elapsed_bytes(const unsigned char *end,const unsigned char *start,uint8_t flips,uint32_t bound) {
    uint8_t i,borrow=0,a_flip=(uint8_t)(flips&7u),b_flip=(uint8_t)(flips>>4);
    int8_t result=0;
    for(i=0;i<8u;++i){
        /* 0 <= 256+a-b-borrow <= 511, even on AVR's 16-bit unsigned int. */
        uint16_t digit=(uint16_t)(256u+(unsigned)end[i^a_flip]-(unsigned)start[i^b_flip]-(unsigned)borrow);
        uint8_t value=(uint8_t)digit,limit=(uint8_t)bound;
        borrow=(uint8_t)(digit<256u);
        if(value!=limit)result=(int8_t)(value<limit?-1:1); /* More significant digit wins. */
        bound>>=8;
    }
    return result; /* Final borrow is discarded, exactly modulo 2^64. */
}
static void elapsed_copy(uint8_t *out,const unsigned char *end,const unsigned char *start,uint8_t flips) {
    uint8_t i,borrow=0,a_flip=(uint8_t)(flips&7u),b_flip=(uint8_t)(flips>>4);
    for(i=0;i<8u;++i){
        uint16_t digit=(uint16_t)(256u+(unsigned)end[i^a_flip]-(unsigned)start[i^b_flip]-(unsigned)borrow);
        out[7u-i]=(uint8_t)digit;borrow=(uint8_t)(digit<256u);
    }
}
static int8_t room_bytes(const unsigned char *value,uint8_t flip,uint32_t delta) {
    uint8_t i;int8_t result=0;
    for(i=0;i<8u;++i){
        uint8_t digit=value[i^flip],limit=(uint8_t)(255u-(unsigned)(uint8_t)delta);
        if(digit!=limit)result=(int8_t)(digit<limit?-1:1);
        delta>>=8;
    }
    return result;
}
static void add_bytes(uint8_t *snapshot,uint32_t delta) {
    uint8_t i,carry=0;
    for(i=0;i<8u;++i){
        uint16_t digit=(uint16_t)((unsigned)snapshot[7u-i]+(unsigned)(uint8_t)delta+(unsigned)carry);
        snapshot[7u-i]=(uint8_t)digit;carry=(uint8_t)(digit>>8);delta>>=8;
    }
}
static void commit_bytes(uint8_t *out,const uint8_t *snapshot) {
    uint8_t i;for(i=0;i<8u;++i)out[7u-i]=snapshot[7u-i];
}
static void native_copy(uint8_t *out,const uint64_t *source) {
    const unsigned char *bytes=(const unsigned char *)source;uint8_t i;
    for(i=0;i<8u;++i)out[7u-i]=bytes[(unsigned)i^HMS_EP_NATIVE_FLIP];
}
#else
static int8_t compare(uint64_t left,uint64_t right) {
    if(left<right)return -1;
    return (int8_t)(left>right);
}
#endif
int8_t hms_ep_encoded_cmp(const uint8_t *left,const uint8_t *right) {
    uint8_t i;
    for(i=0;i<8u;++i)if(left[i]!=right[i])return (int8_t)(left[i]<right[i]?-1:1);
    return 0;
}
uint8_t hms_ep_encoded_absent(const uint8_t *value) {
    uint8_t i,all=255;
    for(i=0;i<8u;++i)all&=value[i];
    return (uint8_t)(all==255u);
}
int8_t hms_ep_time_cmp(const uint64_t *left,const uint64_t *right) {
#if HMS_EP_BYTE_BACKEND
    return byte_compare((const unsigned char *)left,(const unsigned char *)right,NATIVE_PAIR);
#else
    return compare(*left,*right);
#endif
}
int8_t hms_ep_time_cmp_encoded(const uint64_t *left,const uint8_t *right) {
#if HMS_EP_BYTE_BACKEND
    return byte_compare((const unsigned char *)left,right,NATIVE_ENCODED);
#else
    return compare(*left,hms_ep_read64(right));
#endif
}
int8_t hms_ep_elapsed_cmp(const uint64_t *end,const uint64_t *start,uint32_t bound) {
#if HMS_EP_BYTE_BACKEND
    return elapsed_bytes((const unsigned char *)end,(const unsigned char *)start,NATIVE_PAIR,bound);
#else
    return compare(*end-*start,bound);
#endif
}
int8_t hms_ep_elapsed_cmp_encoded(const uint64_t *end,const uint8_t *start,uint32_t bound) {
#if HMS_EP_BYTE_BACKEND
    return elapsed_bytes((const unsigned char *)end,start,NATIVE_ENCODED,bound);
#else
    return compare(*end-hms_ep_read64(start),bound);
#endif
}
int8_t hms_ep_elapsed_encoded_native_cmp(const uint8_t *end,const uint64_t *start,uint32_t bound) {
#if HMS_EP_BYTE_BACKEND
    return elapsed_bytes(end,(const unsigned char *)start,ENCODED_NATIVE,bound);
#else
    return compare(hms_ep_read64(end)-*start,bound);
#endif
}
int8_t hms_ep_elapsed_encoded_cmp(const uint8_t *end,const uint8_t *start,uint32_t bound) {
#if HMS_EP_BYTE_BACKEND
    return elapsed_bytes(end,start,0x77,bound);
#else
    return compare(hms_ep_read64(end)-hms_ep_read64(start),bound);
#endif
}
int8_t hms_ep_add_room_cmp(const uint64_t *value,uint32_t delta) {
#if HMS_EP_BYTE_BACKEND
    return room_bytes((const unsigned char *)value,HMS_EP_NATIVE_FLIP,delta);
#else
    return compare(*value,UINT64_MAX-delta);
#endif
}
void hms_ep_cutoff_min(uint64_t *cutoff,const uint8_t *base,uint32_t delta) {
#if HMS_EP_BYTE_BACKEND
    uint8_t snapshot[8],i;unsigned char *native=(unsigned char *)cutoff;
    memcpy(snapshot,base,8); /* Capture before a possibly overlapping write. */
    if(room_bytes(snapshot,7,delta)<0)add_bytes(snapshot,delta);
    else memset(snapshot,255,8);
    if(byte_compare(snapshot,native,ENCODED_NATIVE)<0)
        for(i=0;i<8u;++i)native[(unsigned)i^HMS_EP_NATIVE_FLIP]=snapshot[7u-i];
#else
    uint64_t at=hms_ep_read64(base);
    uint64_t candidate=at<UINT64_MAX-delta?at+delta:UINT64_MAX;
    if(candidate<*cutoff)*cutoff=candidate;
#endif
}
void hms_ep_write64_sum(uint8_t *p,const uint64_t *source,uint32_t delta) {
#if HMS_EP_BYTE_BACKEND
    uint8_t snapshot[8];native_copy(snapshot,source);add_bytes(snapshot,delta);
    commit_bytes(p,snapshot);
#else
    uint64_t value=*source+delta;hms_ep_write64(p,value);
#endif
}
void hms_ep_write64_encoded_sum(uint8_t *p,const uint8_t *source,uint32_t delta) {
#if HMS_EP_BYTE_BACKEND
    uint8_t snapshot[8];memcpy(snapshot,source,8);add_bytes(snapshot,delta);
    commit_bytes(p,snapshot);
#else
    uint64_t value=hms_ep_read64(source)+delta;hms_ep_write64(p,value);
#endif
}
void hms_ep_write_age(uint8_t *p,const uint64_t *end,const uint8_t *start) {
#if HMS_EP_BYTE_BACKEND
    const unsigned char *bytes=(const unsigned char *)end;
    uint16_t left=(uint16_t)((unsigned)bytes[1u^HMS_EP_NATIVE_FLIP]*256u+(unsigned)bytes[HMS_EP_NATIVE_FLIP]);
    uint16_t right=(uint16_t)((unsigned)start[6]*256u+(unsigned)start[7]);
    write16(p,(uint16_t)(left-right));
#else
    uint16_t value=(uint16_t)(*end-hms_ep_read64(start));write16(p,value);
#endif
}
void hms_ep_write_encoded_age(uint8_t *p,const uint8_t *end,const uint8_t *start) {
#if HMS_EP_BYTE_BACKEND
    uint16_t left=(uint16_t)((unsigned)end[6]*256u+(unsigned)end[7]);
    uint16_t right=(uint16_t)((unsigned)start[6]*256u+(unsigned)start[7]);
    write16(p,(uint16_t)(left-right));
#else
    uint16_t value=(uint16_t)(hms_ep_read64(end)-hms_ep_read64(start));write16(p,value);
#endif
}
void hms_ep_elapsed_snapshot(uint8_t *out,const uint64_t *end,const uint8_t *start) {
#if HMS_EP_BYTE_BACKEND
    uint8_t snapshot[8];elapsed_copy(snapshot,(const unsigned char *)end,start,NATIVE_ENCODED);
    commit_bytes(out,snapshot);
#else
    uint64_t value=*end-hms_ep_read64(start);hms_ep_write64(out,value);
#endif
}
uint8_t hms_ep_duration_sum(uint32_t *out,const uint8_t *duration,uint32_t total) {
    uint32_t low;
    if(duration[0]!=0u || duration[1]!=0u || duration[2]!=0u || duration[3]!=0u)return 0;
    low=hms_ep_read32(duration+4);
    if(low>UINT32_MAX-total)return 0;
    *out=total+low;return 1;
}
