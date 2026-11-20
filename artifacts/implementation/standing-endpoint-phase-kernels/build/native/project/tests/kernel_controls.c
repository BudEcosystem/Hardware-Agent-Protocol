/* Native semantic controls only; never part of the AVR target image. */
#include "../protocol/endpoint/endpoint_kernel.h"
#include <stdio.h>
#include <string.h>

static unsigned assertions;
#define CHECK(x) do{++assertions;if(!(x)){fprintf(stderr,"kernel control line%d: %s\n",__LINE__,#x);return 0;}}while(0)
static void encode(uint8_t *p,uint64_t value,unsigned width) {
    unsigned i;for(i=0;i<width;++i){p[width-1u-i]=(uint8_t)value;value>>=8;}
}
static int order(uint64_t a,uint64_t b) {return (a>b)-(a<b);}
static int numeric_boundaries(void) {
    static const uint64_t values[]={0,1,255,256,65535,65536,UINT64_C(0xffffff),UINT64_C(0x1000000),
        UINT64_C(0xffffffff),UINT64_C(0x100000000),UINT64_C(0xffffffffff),UINT64_C(0x10000000000),
        UINT64_C(0xffffffffffff),UINT64_C(0x1000000000000),UINT64_C(0xffffffffffffff),
        UINT64_C(0x100000000000000),UINT64_C(0x7fffffffffffffff),UINT64_C(0x8000000000000000),
        UINT64_MAX-1u,UINT64_MAX};
    static const uint32_t bounds[]={0,1,60000,UINT32_MAX};
    uint8_t a[8],b[8],out[8],expected[8];unsigned i,j,k;
    for(i=0;i<sizeof(values)/sizeof(values[0]);++i){
        uint64_t left=values[i];encode(a,left,8);
        CHECK(hms_ep_read64(a)==left);CHECK(hms_ep_read32(a+4)==(uint32_t)left);
        hms_ep_write64(out,left);CHECK(memcmp(out,a,8)==0);
        for(j=0;j<sizeof(values)/sizeof(values[0]);++j){
            uint64_t right=values[j];encode(b,right,8);
            CHECK(hms_ep_time_cmp(&left,&right)==order(left,right));
            CHECK(hms_ep_time_cmp_encoded(&left,b)==order(left,right));
            for(k=0;k<sizeof(bounds)/sizeof(bounds[0]);++k){
                uint32_t bound=bounds[k];uint64_t cutoff=left,reference;
                CHECK(hms_ep_elapsed_cmp(&left,&right,bound)==order(left-right,bound));
                CHECK(hms_ep_elapsed_cmp_encoded(&left,b,bound)==order(left-right,bound));
                CHECK(hms_ep_elapsed_encoded_cmp(a,b,bound)==order(left-right,bound));
                CHECK(hms_ep_add_room_cmp(&left,bound)==order(left,UINT64_MAX-bound));
                reference=right<UINT64_MAX-bound?right+bound:UINT64_MAX;
                if(left<reference)reference=left;
                hms_ep_cutoff_min(&cutoff,b,bound);CHECK(cutoff==reference);
                encode(expected,left+bound,8);hms_ep_write64_sum(out,&left,bound);
                CHECK(memcmp(out,expected,8)==0);
                hms_ep_write64_encoded_sum(out,a,bound);CHECK(memcmp(out,expected,8)==0);
            }
            encode(expected,(uint16_t)(left-right),2);hms_ep_write_age(out,&left,b);
            CHECK(memcmp(out,expected,2)==0);
            hms_ep_write_encoded_age(out,a,b);CHECK(memcmp(out,expected,2)==0);
        }
    }
    /* Literal calibration: exact saturation edge and a modulo borrow across
     * all eight bytes must not be turned into a narrowed/signed difference. */
    {
        uint64_t zero=0,one=1,limit=UINT64_MAX;
        uint8_t edge[8]={0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xfe};
        hms_ep_cutoff_min(&limit,edge,1);CHECK(limit==UINT64_MAX);
        CHECK(hms_ep_elapsed_cmp(&zero,&one,UINT32_MAX)==1);
        hms_ep_write_age(out,&zero,edge);CHECK(out[0]==0 && out[1]==2);
    }
    /* Every configured bound gets its exact saturation threshold and elapsed
     * neighbours, including the high half and explicit modulo borrow. */
    for(k=0;k<sizeof(bounds)/sizeof(bounds[0]);++k){
        uint32_t bound=bounds[k];uint64_t threshold=UINT64_MAX-bound;unsigned position;
        for(position=0;position<3u;++position){
            uint64_t at,cutoff=UINT64_MAX;
            if(position==2u && bound==0u)continue; /* M+1 is outside the domain. */
            at=position==0u?threshold-1u:(position==1u?threshold:threshold+1u);
            encode(a,at,8);hms_ep_cutoff_min(&cutoff,a,bound);
            CHECK(cutoff==(position==0u?UINT64_MAX-1u:UINT64_MAX));
            CHECK(hms_ep_add_room_cmp(&at,bound)==(int)position-1);
            cutoff=UINT64_MAX-2u;hms_ep_cutoff_min(&cutoff,a,bound);CHECK(cutoff==UINT64_MAX-2u);
        }
        for(position=0;position<3u;++position){
            uint64_t start=UINT64_C(0x8123456700000000),delta,end;
            if(position==0u && bound==0u)continue;
            delta=position==0u?(uint64_t)bound-1u:(position==1u?bound:(uint64_t)bound+1u);
            end=start+delta;encode(a,end,8);encode(b,start,8);
            CHECK(hms_ep_elapsed_cmp(&end,&start,bound)==(int)position-1);
            CHECK(hms_ep_elapsed_cmp_encoded(&end,b,bound)==(int)position-1);
            CHECK(hms_ep_elapsed_encoded_cmp(a,b,bound)==(int)position-1);
            /* The same modular delta when end is numerically below start. */
            if(delta!=0u){
                end=0;start=UINT64_MAX-delta+1u;encode(a,end,8);encode(b,start,8);
                CHECK(end<start);
                CHECK(hms_ep_elapsed_cmp(&end,&start,bound)==(int)position-1);
                CHECK(hms_ep_elapsed_cmp_encoded(&end,b,bound)==(int)position-1);
                CHECK(hms_ep_elapsed_encoded_cmp(a,b,bound)==(int)position-1);
            }
        }
    }
    return 1;
}
static int overlapping_snapshots(void) {
    union {uint64_t native;uint8_t bytes[24];} actual,expected;
    unsigned offset;
    for(offset=0;offset<8u;++offset){
        uint64_t snapshot;
        memset(&actual,0xa5,sizeof(actual));actual.native=UINT64_C(0x81234567fffffff8);
        memcpy(&expected,&actual,sizeof(actual));snapshot=expected.native;
        encode(expected.bytes+offset,snapshot,8);
        hms_ep_write64_snapshot(actual.bytes+offset,&actual.native);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
        memset(&actual,0xa5,sizeof(actual));actual.native=UINT64_MAX-2u;
        memcpy(&expected,&actual,sizeof(actual));snapshot=expected.native;
        encode(expected.bytes+offset,snapshot+4u,8);
        hms_ep_write64_sum(actual.bytes+offset,&actual.native,4);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
        memset(actual.bytes,0xa5,sizeof(actual));encode(actual.bytes+8,UINT64_C(0x7fffffffffffffff),8);
        memcpy(expected.bytes,actual.bytes,sizeof(actual));
        encode(expected.bytes+offset,UINT64_C(0x8000000000000000),8);
        hms_ep_write64_encoded_sum(actual.bytes+offset,actual.bytes+8,1);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
    }
    return 1;
}
static void reference_context(uint8_t *p,const hms_endpoint *e) {
    uint16_t handle;
    encode(p,e->control_generation,4);handle=e->context_handle;
    p[4]=(uint8_t)(handle>>8);p[5]=(uint8_t)handle;memcpy(p+6,e->context_digest,32);
}
static void reference_tail(uint8_t *p,const hms_endpoint *e) {
    encode(p,e->now_tick,8);encode(p+8,e->armed_until,8);
    encode(p+16,e->call_high_water,4);p[20]=e->receipt.held_mask;
}
static int sequential_wire_groups(void) {
    hms_endpoint a,b;uint8_t out[48],expected[48],report[32],observation[24];unsigned i;
    memset(&a,0,sizeof(a));a.control_generation=UINT32_C(0x81234567);a.context_handle=0xabcd;
    a.now_tick=UINT64_C(0x81234567fffffff8);a.armed_until=UINT64_C(0xfedcba9876543210);
    a.call_high_water=UINT32_C(0xcafefeed);a.receipt.held_mask=0x81;
    for(i=0;i<32u;++i)a.context_digest[i]=(uint8_t)(0x40u+i);
    memset(out,0xa5,sizeof(out));memset(expected,0xa5,sizeof(expected));
    hms_ep_write_context(out,&a);reference_context(expected,&a);CHECK(memcmp(out,expected,sizeof(out))==0);
    hms_ep_write_finite_tail(out,&a);reference_tail(expected,&a);CHECK(memcmp(out,expected,sizeof(out))==0);
    /* Valid overlap: context destination ends before the digest source;
     * finite tail deliberately changes a later scalar before its later read. */
    memcpy(&b,&a,sizeof(a));
    hms_ep_write_context((uint8_t *)&a+offsetof(hms_endpoint,context_digest)-38u,&a);
    reference_context((uint8_t *)&b+offsetof(hms_endpoint,context_digest)-38u,&b);
    CHECK(memcmp(&a,&b,sizeof(a))==0);
    hms_ep_write_finite_tail((uint8_t *)&a+offsetof(hms_endpoint,now_tick)+1u,&a);
    reference_tail((uint8_t *)&b+offsetof(hms_endpoint,now_tick)+1u,&b);
    CHECK(memcmp(&a,&b,sizeof(a))==0);
    for(i=0;i<32u;++i)report[i]=(uint8_t)i;
    hms_ep_commit_observation(observation,report);
    for(i=0;i<4u;++i)CHECK(observation[i]==28u+i);
    for(i=0;i<8u;++i)CHECK(observation[4u+i]==20u+i);
    for(i=0;i<4u;++i){CHECK(observation[12u+i]==16u+i);CHECK(observation[16u+i]==12u+i);}
    CHECK(observation[20]==1u && observation[21]==1u && observation[22]==1u && observation[23]==0u);
    return 1;
}
/* These additional controls compare the selected implementation to scalar
 * expressions, including upper-half differences with equal low32 values. */
static int byte_digit_boundaries(void) {
    static const uint32_t limits[]={0,1,60000,INT32_MAX,UINT32_MAX};
    unsigned position,digit,which;uint8_t encoded[8],other[8],duration[8],expected[8];
    CHECK(HMS_EP_BYTE_BACKEND==0 || HMS_EP_BYTE_BACKEND==1);
    for(position=0;position<8u;++position)for(digit=0;digit<256u;++digit){
        uint64_t left=(uint64_t)digit<<(position*8u);
        uint64_t right=left-1u;
        encode(encoded,left,8);encode(other,right,8);
        CHECK(hms_ep_encoded_cmp(encoded,other)==order(left,right));
        CHECK(hms_ep_encoded_absent(encoded)==(uint8_t)(left==UINT64_MAX));
        CHECK(hms_ep_time_cmp(&left,&right)==order(left,right));
        CHECK(hms_ep_time_cmp_encoded(&left,other)==order(left,right));
        hms_ep_elapsed_snapshot(duration,&left,other);encode(expected,left-right,8);
        CHECK(memcmp(duration,expected,8)==0);
        for(which=0;which<sizeof(limits)/sizeof(limits[0]);++which){
            uint32_t bound=limits[which];
            CHECK(hms_ep_elapsed_encoded_native_cmp(encoded,&right,bound)==order(left-right,bound));
            CHECK(hms_ep_elapsed_cmp(&left,&right,bound)==order(left-right,bound));
            CHECK(hms_ep_elapsed_cmp_encoded(&left,other,bound)==order(left-right,bound));
            CHECK(hms_ep_elapsed_encoded_cmp(encoded,other,bound)==order(left-right,bound));
            /* Reverse subtraction forces a full-width borrow for almost all
             * patterns; none of its upper four bytes may be discarded. */
            CHECK(hms_ep_elapsed_encoded_native_cmp(other,&left,bound)==order(right-left,bound));
        }
        right=left^UINT64_C(0x8000000000000000);encode(other,right,8);
        CHECK((uint32_t)left==(uint32_t)right);
        CHECK(hms_ep_elapsed_encoded_native_cmp(encoded,&right,UINT32_MAX)==1);
        {
            uint64_t low=position==0u?0u:(UINT64_C(1)<<(position*8u))-1u;
            uint64_t value=((uint64_t)digit<<(position*8u))|low;
            uint64_t cutoff=UINT64_MAX,reference=value<UINT64_MAX-1u?value+1u:UINT64_MAX;
            uint8_t sum[8],base[8];
            /* Carry crosses every lower digit, then this digit when it is
             * 255; position7/digit255 wraps all eight bytes to zero. */
            encode(base,value,8);encode(expected,value+1u,8);
            hms_ep_write64_sum(sum,&value,1);CHECK(memcmp(sum,expected,8)==0);
            hms_ep_write64_encoded_sum(sum,base,1);CHECK(memcmp(sum,expected,8)==0);
            CHECK(hms_ep_add_room_cmp(&value,1)==order(value,UINT64_MAX-1u));
            hms_ep_cutoff_min(&cutoff,base,1);CHECK(cutoff==reference);
        }
    }
    /* INT32_MAX is an additional contract bound, absent from the retained old
     * table. Exercise exact neighbours without modifying that old control. */
    for(position=0;position<3u;++position){
        uint64_t threshold=UINT64_MAX-INT32_MAX;
        uint64_t at=position==0u?threshold-1u:(position==1u?threshold:threshold+1u);
        uint64_t cutoff=UINT64_MAX,start=UINT64_C(0x8123456700000000);
        uint64_t delta=position==0u?(uint64_t)INT32_MAX-1u:(position==1u?(uint64_t)INT32_MAX:(uint64_t)INT32_MAX+1u);
        uint64_t end=start+delta;
        encode(encoded,at,8);hms_ep_cutoff_min(&cutoff,encoded,INT32_MAX);
        CHECK(cutoff==(position==0u?UINT64_MAX-1u:UINT64_MAX));
        CHECK(hms_ep_add_room_cmp(&at,INT32_MAX)==(int)position-1);
        encode(encoded,end,8);encode(other,start,8);
        CHECK(hms_ep_elapsed_cmp(&end,&start,INT32_MAX)==(int)position-1);
        CHECK(hms_ep_elapsed_cmp_encoded(&end,other,INT32_MAX)==(int)position-1);
        CHECK(hms_ep_elapsed_encoded_cmp(encoded,other,INT32_MAX)==(int)position-1);
        CHECK(hms_ep_elapsed_encoded_native_cmp(encoded,&start,INT32_MAX)==(int)position-1);
        end=0;start=UINT64_MAX-delta+1u;encode(encoded,end,8);encode(other,start,8);
        CHECK(hms_ep_elapsed_cmp(&end,&start,INT32_MAX)==(int)position-1);
        CHECK(hms_ep_elapsed_encoded_native_cmp(encoded,&start,INT32_MAX)==(int)position-1);
    }
    memset(encoded,255,8);CHECK(hms_ep_encoded_absent(encoded)==1u);
    for(position=0;position<8u;++position){encoded[position]=254;CHECK(hms_ep_encoded_absent(encoded)==0u);encoded[position]=255;}
    return 1;
}
static int elapsed_overlap_and_account(void) {
    static const uint32_t totals[]={0,1,UINT32_MAX-1u,UINT32_MAX};
    static const uint64_t values[]={0,1,UINT32_MAX-1u,UINT32_MAX,UINT64_C(0x100000000),UINT64_MAX};
    union {uint64_t native;uint8_t bytes[32];} actual,expected;
    uint8_t duration[8];unsigned offset,i,j;
    for(offset=0;offset<=16u;++offset){
        uint64_t saved_end,saved_start;
        memset(&actual,0xa5,sizeof(actual));actual.native=UINT64_C(0x8123456700000000);
        encode(actual.bytes+8,UINT64_C(0xfedcba98ffffffff),8);memcpy(&expected,&actual,sizeof(actual));
        saved_end=expected.native;saved_start=UINT64_C(0xfedcba98ffffffff);
        encode(expected.bytes+offset,saved_end-saved_start,8);
        hms_ep_elapsed_snapshot(actual.bytes+offset,&actual.native,actual.bytes+8);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
    }
    for(i=0;i<sizeof(totals)/sizeof(totals[0]);++i)for(j=0;j<sizeof(values)/sizeof(values[0]);++j){
        uint32_t out=UINT32_C(0xa55aa55a),total=totals[i];uint8_t valid;
        encode(duration,values[j],8);valid=hms_ep_duration_sum(&out,duration,total);
        CHECK(valid==(uint8_t)(values[j]<=UINT32_MAX-total));
        CHECK(out==(valid!=0u?total+(uint32_t)values[j]:UINT32_C(0xa55aa55a)));
    }
    return 1;
}
static int cutoff_and_age_overlap(void) {
    union {uint64_t native;uint8_t bytes[32];} actual,expected;
    unsigned offset;uint8_t base[8];
    for(offset=0;offset<16u;++offset){
        uint64_t cutoff,encoded_base,candidate;unsigned i;
        memset(&actual,0x81,sizeof(actual));actual.native=UINT64_C(0xfedcba9876543210);
        memcpy(&expected,&actual,sizeof(actual));memcpy(base,expected.bytes+offset,8);
        encoded_base=0;for(i=0;i<8u;++i)encoded_base=(encoded_base<<8)|base[i];
        cutoff=expected.native;candidate=encoded_base<UINT64_MAX-60000u?encoded_base+60000u:UINT64_MAX;
        if(candidate<cutoff)cutoff=candidate;
        expected.native=cutoff;
        hms_ep_cutoff_min(&actual.native,actual.bytes+offset,60000);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
        memset(&actual,0xa5,sizeof(actual));actual.native=UINT64_C(0x8123456700000000);
        encode(actual.bytes+8,UINT64_C(0xfedcba98ffffffff),8);memcpy(&expected,&actual,sizeof(actual));
        encode(expected.bytes+offset,(uint16_t)(UINT64_C(0x8123456700000000)-UINT64_C(0xfedcba98ffffffff)),2);
        hms_ep_write_age(actual.bytes+offset,&actual.native,actual.bytes+8);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
        encode(actual.bytes,UINT64_C(0x8123456700000000),8);encode(actual.bytes+8,UINT64_C(0xfedcba98ffffffff),8);
        memcpy(&expected,&actual,sizeof(actual));encode(expected.bytes+offset,1,2);
        hms_ep_write_encoded_age(actual.bytes+offset,actual.bytes,actual.bytes+8);
        CHECK(memcmp(&actual,&expected,sizeof(actual))==0);
    }
    return 1;
}
int main(void) {
    if(!numeric_boundaries() || !overlapping_snapshots() || !sequential_wire_groups() ||
            !byte_digit_boundaries() || !elapsed_overlap_and_account() || !cutoff_and_age_overlap())return 1;
    printf("{\"cases\":6,\"old_cases\":3,\"backend\":%u,\"assertions\":%u,\"physical_qualification\":false}\n",
        (unsigned)HMS_EP_BYTE_BACKEND,assertions);return 0;
}
