/* Native controls for the isolated profile. Source only until parent review.
 * These are simulation oracles, not hardware qualification. */
#include "standing_fixture.h"
#include "standing_vectors.h"
#include "../protocol/endpoint/link.h"
#include <stdio.h>
#include <string.h>

static unsigned assertions;
#define CHECK(x) do{++assertions;if(!(x)){fprintf(stderr,"standing control failed line%d: %s\n",__LINE__,#x);return 0;}}while(0)
typedef struct {
    hms_endpoint e;hms_standing s;hms_st_arena arena;
    hms_ep_config finite;hms_st_config controller;hms_endpoint_link link;
    uint32_t request;uint8_t out[192];uint16_t length;
} world;
static world w;
static uint32_t r32(const uint8_t *p){return hms_st_fixture_read32(p);}
static uint64_t r64(const uint8_t *p){return hms_st_fixture_read64(p);}
static void p32(uint8_t *p,uint32_t v){hms_st_fixture_write32(p,v);}
static void p64(uint8_t *p,uint64_t v){hms_st_fixture_write64(p,v);}
static void p16(uint8_t *p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static int call(const uint8_t *p,uint16_t n){
    uint64_t session=p[1]==ST_DESCRIBE && p[0]==2u?0u:1u;
    uint16_t f=(uint16_t)(((uint16_t)w.arena.driver[FX_FLAGS]<<8)|w.arena.driver[FX_FLAGS+1]);
    ++w.request;w.length=0;
    if(hms_endpoint_handle(&w.e,1,0,session,w.request,p,n,r64(w.arena.driver+FX_CLOCK),f,w.out,&w.length)==0u)return -1;
    return w.length>=7u?w.out[6]:-2;
}
static void tick(uint64_t n){
    uint16_t f=(uint16_t)(((uint16_t)w.arena.driver[FX_FLAGS]<<8)|w.arena.driver[FX_FLAGS+1]);
    p64(w.arena.driver+FX_CLOCK,n);hms_endpoint_poll(&w.e,n,f);
}
static void cycle(uint64_t n){tick(n);tick(n+1u);tick(n+2u);}
static void mutation_bytes(uint8_t *p,uint8_t op){
    memset(p,0,66);memcpy(p,golden_open,44);p[1]=op;
    p32(p+44,r32(w.s.bytes+ST_MUT)+1u);p32(p+48,r32(w.s.bytes+ST_REV));
}
static int setup(void){
    uint8_t bind[72];uint8_t i;
    memset(&w,0,sizeof(w));hms_st_fixture_init(&w.arena,&w.finite,&w.controller);
    CHECK(hms_endpoint_init(&w.e,&w.finite,1,0,25)==1u);
    CHECK(hms_standing_attach(&w.s,&w.e,&w.controller,&w.arena)==1u);
    CHECK(hms_standing_attach(&w.s,&w.e,&w.controller,&w.arena)==0u);
    hms_endpoint_link_init(&w.link);
    memset(bind,0,72);bind[0]=2;bind[1]=ST_BIND;p32(bind+2,1);p16(bind+6,1);
    for(i=0;i<32u;++i)bind[8u+i]=(uint8_t)(0xc0u+i);
    memset(bind+40,0x55,32);CHECK(call(bind,72)==HMS_EP_OK);
    CHECK(w.e.control_generation==2u && w.length==182u && w.out[7]==1u);
    return 1;
}
static int opened(void){
    CHECK(setup());CHECK(call(golden_open,134)==HMS_EP_OK);
    CHECK(w.length==190u && memcmp(w.out,golden_open_reply,190)==0);
    CHECK(sizeof(w.arena)==256u && sizeof(w.s.bytes)==128u);
    CHECK(w.e.operation_length==134u && w.s.bytes[ST_SLOT]==ST_STANDING);
    CHECK(w.e.fence_floor[0]==1u && w.e.fence_floor[1]==1u);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u);return 1;
}
static int prepared(void){
    CHECK(opened());cycle(0);
    CHECK(w.s.bytes[ST_LIFE]==ST_PREPARED);
    CHECK(r32(w.arena.observation[0]+12)==1u && r32(w.arena.observation[1]+12)==1u);
    CHECK(call(golden_start,66)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && r32(w.s.bytes+ST_REV)==2u);
    return 1;
}
static int first_transition(void){
    CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);cycle(12);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==1u && w.arena.driver[FX_OUTPUT]==1u);
    CHECK(w.s.bytes[ST_COUNT]==1u && w.s.bytes[ST_PENDING]==0u);
    CHECK((w.arena.record[0][40]&7u)==ST_RECORD_PENDING);
    CHECK(r64(w.arena.record[0]+26)==UINT64_MAX);
    cycle(24);CHECK(w.s.bytes[ST_PENDING]==255u);
    CHECK((w.arena.record[0][40]&7u)==ST_RECORD_SUCCESS);
    CHECK(r64(w.arena.record[0]+26)>r64(w.arena.record[0]+4));return 1;
}
static int full_ledger(void){
    CHECK(first_transition());p32(w.arena.driver+FX_DEMAND,15000);cycle(36);cycle(48);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==2u && w.s.bytes[ST_COUNT]==2u);
    CHECK((w.arena.record[1][40]&7u)==ST_RECORD_SUCCESS);
    p32(w.arena.driver+FX_DEMAND,35000);cycle(60);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_REASON+1]==ST_LEDGER);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==2u);
    tick(63);tick(64);
    CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && w.s.bytes[ST_OWNED]==3u && w.s.bytes[ST_QUIET]==3u);
    CHECK(w.s.bytes[ST_COUNT]==2u && r32(w.arena.driver+FX_LOSSES)==1u);
    CHECK(w.s.bytes[ST_WITNESS+2]==HMS_EP_SIMULATION && w.s.bytes[ST_WITNESS+3]==HMS_EP_UNVERIFIED);
    return 1;
}

static int wire_and_refusals(void){
    uint8_t p[134],saved[128],q[49];uint32_t floors[8];
    CHECK(setup());memcpy(p,golden_open,134);memcpy(floors,w.e.fence_floor,sizeof(floors));
    CHECK(call(p,133)==HMS_EP_BAD_LENGTH);CHECK(w.s.bytes[ST_SLOT]==ST_EMPTY);
    p[91]=1;CHECK(call(p,134)==HMS_EP_RESERVED);p[91]=0;
    CHECK(memcmp(floors,w.e.fence_floor,sizeof(floors))==0);
    p[133]=2;CHECK(call(p,134)==ST_SOURCE_INVALID);p[133]=1;
    CHECK(w.e.operation_length==0u && r32(w.s.bytes+ST_HIGH)==0u);
    CHECK(call(p,134)==HMS_EP_OK);memcpy(saved,w.s.bytes,128);
    CHECK(call(p,134)==HMS_EP_OK && memcmp(saved,w.s.bytes,128)==0);
    p[119]^=1u;CHECK(call(p,134)==HMS_EP_CONFLICT);p[119]^=1u;
    CHECK(memcmp(saved,w.s.bytes,128)==0);
    memcpy(q,golden_open,44);q[1]=ST_STATUS;memset(q+44,0,5);
    CHECK(call(q,49)==HMS_EP_OK && w.length==190u);
    CHECK(r32(w.out+2)==w.request && r32(w.out+14)==1u && w.out[66]==ST_STANDING);
    q[44]=1;CHECK(call(q,49)==HMS_EP_OK && w.length==114u);
    q[44]=2;p32(q+45,1);CHECK(call(q,49)==HMS_EP_NOT_SEEN && w.length==66u);
    q[44]=3;CHECK(call(q,49)==ST_BAD_PAGE);
    p[0]=1;p[1]=1;CHECK(call(p,2)==HMS_EP_UNSUPPORTED && w.length==7u);
    p[1]=16;CHECK(call(p,72)==HMS_EP_UNSUPPORTED);
    p[1]=17;CHECK(call(p,48)==HMS_EP_UNSUPPORTED);
    p[1]=32;CHECK(call(p,96)==HMS_EP_UNSUPPORTED);
    p[1]=33;CHECK(call(p,44)==HMS_EP_UNSUPPORTED);
    p[1]=34;CHECK(call(p,44)==HMS_EP_UNSUPPORTED);
    p[1]=35;CHECK(call(p,44)==HMS_EP_UNSUPPORTED);
    CHECK(memcmp(saved,w.s.bytes,128)==0 && r32(w.arena.driver+FX_DISPATCHES)==0u);
    return 1;
}
static int replay_and_renewal(void){
    uint8_t p[66],saved[66],open[134];uint32_t revision;
    CHECK(prepared());mutation_bytes(p,ST_RENEW);p64(p+52,2000);memcpy(saved,p,66);
    CHECK(call(p,66)==HMS_EP_OK);revision=r32(w.s.bytes+ST_REV);
    CHECK(r64(w.s.bytes+ST_LEASE)==2000u);
    CHECK(call(saved,66)==HMS_EP_OK && r32(w.s.bytes+ST_REV)==revision);
    p[51]^=1u;CHECK(call(p,66)==HMS_EP_CONFLICT);p[51]^=1u;
    memcpy(open,golden_open,134);CHECK(call(open,134)==HMS_EP_OK);
    open[119]^=1u;CHECK(call(open,134)==HMS_EP_CONFLICT);
    tick(2000);CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && r32(w.s.bytes+ST_REV)>revision);
    revision=r32(w.s.bytes+ST_REV);
    CHECK(call(saved,66)==HMS_EP_OK && r32(w.s.bytes+ST_REV)==revision);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && r64(w.s.bytes+ST_LEASE)==2000u);
    mutation_bytes(p,ST_RENEW);p64(p+52,3000);CHECK(call(p,66)==HMS_EP_BAD_STATE);
    CHECK(r32(w.s.bytes+ST_MUT)==2u);return 1;
}
static int encoded_time_boundaries(void){
    /* Full controller timelines, with literal byte oracles independent of
     * r64/p64: cross a 32-bit carry with bit63 set, then run near UINT64_MAX.
     * Columns are OPEN/RENEW/RESUME leases, dispatch, loss handoff, witness. */
    static const uint64_t bases[2]={UINT64_C(0x81234567fffffff8),UINT64_C(0xffffffffffffefff)};
    static const uint8_t expected[2][6][8]={
        {{0x81,0x23,0x45,0x68,0,0,0x03,0xe0},{0x81,0x23,0x45,0x68,0,0,0x07,0xc8},
         {0x81,0x23,0x45,0x68,0,0,0x0b,0xb0},{0x81,0x23,0x45,0x68,0,0,0,0x06},
         {0x81,0x23,0x45,0x68,0,0,0,0x07},{0x81,0x23,0x45,0x68,0,0,0,0x08}},
        {{0xff,0xff,0xff,0xff,0xff,0xff,0xf3,0xe7},{0xff,0xff,0xff,0xff,0xff,0xff,0xf7,0xcf},
         {0xff,0xff,0xff,0xff,0xff,0xff,0xfb,0xb7},{0xff,0xff,0xff,0xff,0xff,0xff,0xf0,0x0d},
         {0xff,0xff,0xff,0xff,0xff,0xff,0xf0,0x0e},{0xff,0xff,0xff,0xff,0xff,0xff,0xf0,0x0f}}
    };
    static const uint8_t absent[8]={0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff};
    uint8_t open[134],p[66],q[49];unsigned which;uint32_t revision;
    for(which=0;which<2u;++which){
        uint64_t base=bases[which];
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);
        memcpy(open,golden_open,sizeof(open));memcpy(open+112,expected[which][0],8);
        CHECK(call(open,134)==HMS_EP_OK && w.length==190u);
        CHECK(memcmp(w.s.bytes+ST_LEASE,expected[which][0],8)==0 && memcmp(w.out+95,expected[which][0],8)==0);
        CHECK(memcmp(w.s.bytes+ST_LOSS_AT,absent,8)==0 && memcmp(w.s.bytes+ST_CLEANUP,absent,8)==0);
        CHECK(memcmp(w.s.bytes+ST_QUIET_AT,absent,8)==0 && memcmp(w.arena.work+8,absent,8)==0);
        cycle(base);CHECK(call(golden_start,66)==HMS_EP_OK);
        p32(w.arena.driver+FX_DEMAND,35000);cycle(base+12u);
        CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && w.s.bytes[ST_PENDING]==0u);
        CHECK(memcmp(w.arena.record[0]+4,expected[which][3],8)==0 && memcmp(w.arena.work,expected[which][3],8)==0);
        CHECK(memcmp(w.arena.record[0]+26,absent,8)==0 && w.arena.record[0][25]==2u && w.arena.record[0][34]==0u);
        CHECK(r64(w.arena.work+8)==base+64u && r32(w.arena.driver+FX_DISPATCHES)==1u);
        mutation_bytes(p,ST_RENEW);memcpy(p+52,absent,8);revision=r32(w.s.bytes+ST_REV);
        CHECK(call(p,66)==HMS_EP_LEASE_INVALID && r32(w.s.bytes+ST_REV)==revision);
        CHECK(memcmp(w.s.bytes+ST_LEASE,expected[which][0],8)==0);
        memcpy(p+52,expected[which][1],8);CHECK(call(p,66)==HMS_EP_OK);
        CHECK(memcmp(w.s.bytes+ST_LEASE,expected[which][1],8)==0);
        revision=r32(w.s.bytes+ST_REV);CHECK(call(p,66)==HMS_EP_OK && r32(w.s.bytes+ST_REV)==revision);
        mutation_bytes(p,ST_SUSPEND_OP);p16(p+64,ST_SUSPEND);CHECK(call(p,66)==HMS_EP_OK);
        CHECK(r64(w.s.bytes+ST_LOSS_AT)==base+14u && w.s.bytes[ST_OWNED]==3u);
        tick(base+15u);CHECK(memcmp(w.s.bytes+ST_QUIET_AT,expected[which][4],8)==0 && w.s.bytes[ST_LOSS_COMMAND]==3u);
        memcpy(q,golden_open,44);q[1]=ST_STATUS;memset(q+44,0,5);
        CHECK(call(q,49)==HMS_EP_OK && memcmp(w.out+135,absent,8)==0);
        CHECK(memcmp(w.s.bytes+ST_QUIET_AT,expected[which][4],8)==0 && r64(w.s.bytes+ST_LOSS_AT)==base+14u);
        tick(base+16u);CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && w.s.bytes[ST_QUIET]==3u);
        CHECK(memcmp(w.s.bytes+ST_QUIET_AT,expected[which][5],8)==0 && r32(w.s.bytes+ST_ACCOUNT)==2u);
        mutation_bytes(p,ST_ACKNOWLEDGE);p32(p+60,1);CHECK(call(p,66)==HMS_EP_OK);
        mutation_bytes(p,ST_RESUME);memcpy(p+52,expected[which][2],8);CHECK(call(p,66)==HMS_EP_OK);
        CHECK(w.s.bytes[ST_LIFE]==ST_PREPARED && memcmp(w.s.bytes+ST_LEASE,expected[which][2],8)==0);
        CHECK(memcmp(w.arena.work,expected[which][5],8)==0 && memcmp(w.arena.work+8,absent,8)==0);
        CHECK(memcmp(w.s.bytes+ST_LOSS_AT,absent,8)==0 && memcmp(w.s.bytes+ST_CLEANUP,absent,8)==0 && memcmp(w.s.bytes+ST_QUIET_AT,absent,8)==0);
        CHECK(r32(w.s.bytes+ST_ACT)==1u && r32(w.s.bytes+ST_ACK)==1u && r32(w.arena.driver+FX_DISPATCHES)==1u);
        cycle(base+17u);mutation_bytes(p,ST_START);CHECK(call(p,66)==HMS_EP_OK);
        cycle(base+29u);CHECK(r32(w.s.bytes+ST_ACT)==2u && r32(w.arena.driver+FX_DISPATCHES)==2u);
        CHECK(r32(w.arena.driver+FX_LOSSES)==1u && w.s.bytes[ST_OWNED]==3u);
    }
    CHECK(prepared());w.arena.driver[FX_INJECT]=FX_CLOCK_LOSS;tick(12);
    CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && w.s.bytes[ST_OWNED]==3u);
    CHECK(memcmp(w.s.bytes+ST_LOSS_AT,absent,8)==0 && memcmp(w.s.bytes+ST_CLEANUP,absent,8)==0);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u);return 1;
}
static int ledger_ack_resume(void){
    uint8_t p[66],observations[48],records[88];uint32_t activation;
    CHECK(full_ledger());memcpy(observations,w.arena.observation,48);memcpy(records,w.arena.record,88);
    tick(65);CHECK(memcmp(observations,w.arena.observation,48)==0 && memcmp(records,w.arena.record,88)==0);
    mutation_bytes(p,ST_RESUME);p64(p+52,2000);CHECK(call(p,66)==HMS_EP_BAD_STATE);
    mutation_bytes(p,ST_ACKNOWLEDGE);p32(p+60,2);CHECK(call(p,66)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_COUNT]==0u && w.s.bytes[ST_OWNED]==3u);
    CHECK(r32(w.s.bytes+ST_ACK)==2u && r32(w.s.bytes+ST_ACT)==2u);
    activation=r32(w.s.bytes+ST_ACT);
    mutation_bytes(p,ST_RESUME);p64(p+52,2000);CHECK(call(p,66)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_LIFE]==ST_PREPARED && r32(w.s.bytes+ST_ACT)==activation);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==2u);
    mutation_bytes(p,ST_START);CHECK(call(p,66)==ST_SOURCE_INVALID);
    cycle(66);mutation_bytes(p,ST_START);CHECK(call(p,66)==HMS_EP_OK);
    cycle(78);CHECK(r32(w.s.bytes+ST_ACT)==3u && r32(w.arena.driver+FX_DISPATCHES)==3u);
    CHECK(r32(w.s.bytes+ST_ACCOUNT)==24u);return 1;
}
static int pending_ack_and_feedback(void){
    uint8_t p[66];
    CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);cycle(12);
    mutation_bytes(p,ST_ACKNOWLEDGE);p32(p+60,1);CHECK(call(p,66)==ST_ACK_PENDING);
    CHECK(w.s.bytes[ST_COUNT]==1u && r32(w.s.bytes+ST_MUT)==1u);
    p32(w.arena.driver+FX_FEEDBACK,100);cycle(24);cycle(36);cycle(48);cycle(60);
    tick(64);CHECK(w.s.bytes[ST_REASON+1]==ST_FEEDBACK);
    CHECK((w.arena.record[0][40]&7u)==ST_RECORD_FAILED);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING);return 1;
}
static int feedback_signed_range(void){
    uint8_t open[134];unsigned reverse;
    for(reverse=0;reverse<2u;++reverse){
        uint32_t before=reverse!=0u?(uint32_t)(-INT32_C(99999)):UINT32_C(200000);
        uint32_t after=reverse!=0u?UINT32_C(200000):(uint32_t)(-INT32_C(100000));
        CHECK(setup());memcpy(open,golden_open,sizeof(open));
        p32(open+47,reverse!=0u?(uint32_t)(-INT32_C(100000)):UINT32_C(199999));
        p32(open+51,before);p32(open+55,reverse!=0u?1u:300000u);
        /* Keep a successful ON transition from immediately triggering OFF
         * while its signed improvement and retained evidence are inspected. */
        p16(open+69,100);CHECK(call(open,134)==HMS_EP_OK);
        cycle(0);CHECK(call(golden_start,66)==HMS_EP_OK);
        p32(w.arena.driver+FX_DEMAND,before);cycle(12);
        CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && w.s.bytes[ST_COUNT]==1u && w.s.bytes[ST_PENDING]==0u);
        CHECK(r64(w.arena.record[0]+4)==14u && r32(w.arena.work+16)==before);
        CHECK(r32(w.arena.driver+FX_DISPATCHES)==1u && w.arena.driver[FX_OUTPUT]==1u);
        p32(w.arena.driver+FX_DEMAND,after);p32(w.arena.driver+FX_FEEDBACK,1000);cycle(24);
        CHECK(r32(w.arena.observation[0])==after && r32(w.arena.record[0]+34)==1000u);
        CHECK(r64(w.arena.record[0]+26)==25u && w.s.bytes[ST_OWNED]==3u);
        if(reverse==0u){
            CHECK((w.arena.record[0][40]&7u)==ST_RECORD_SUCCESS && w.s.bytes[ST_PENDING]==255u);
            CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && w.s.bytes[ST_COUNT]==1u);
            CHECK(r32(w.arena.driver+FX_DISPATCHES)==1u && r32(w.arena.driver+FX_LOSSES)==0u);
        }else{
            CHECK((w.arena.record[0][40]&7u)==ST_RECORD_PENDING && w.s.bytes[ST_PENDING]==0u);
            cycle(36);cycle(48);cycle(60);tick(64);
            CHECK((w.arena.record[0][40]&7u)==ST_RECORD_FAILED && w.s.bytes[ST_PENDING]==255u);
            CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_REASON+1]==ST_FEEDBACK);
            CHECK(r32(w.arena.driver+FX_DISPATCHES)==1u && w.s.bytes[ST_OWNED]==3u);
            tick(65);p32(w.arena.driver+FX_FEEDBACK,0);tick(66);
            CHECK(w.s.bytes[ST_LIFE]==ST_STOPPED && w.s.bytes[ST_QUIET]==3u);
            CHECK(w.s.bytes[ST_COUNT]==1u && w.s.bytes[ST_OWNED]==3u && r32(w.arena.driver+FX_LOSSES)==1u);
        }
    }
    return 1;
}
static int source_and_clock_faults(void){
    uint8_t p[66];uint32_t sequence;
    CHECK(prepared());sequence=r32(w.arena.observation[0]+12);
    w.arena.driver[FX_INJECT]=FX_BAD_EPOCH;tick(12);
    CHECK(w.s.bytes[ST_REASON+1]==ST_EPOCH_LOSS && r32(w.arena.observation[0]+12)==sequence);
    CHECK(r32(w.s.bytes+ST_EPOCH)==1u && r32(w.arena.driver+FX_DISPATCHES)==0u);
    CHECK(prepared());w.arena.driver[FX_INJECT]=FX_FALSE_PHYSICAL;tick(12);
    CHECK(w.s.bytes[ST_REASON+1]==ST_QUALITY && r32(w.arena.driver+FX_DISPATCHES)==0u);
    CHECK(prepared());p32(w.arena.driver+FX_EPOCH,2);mutation_bytes(p,ST_RENEW);p64(p+52,2000);
    CHECK(call(p,66)==ST_SOURCE_INVALID && w.s.bytes[ST_LIFE]==ST_DRAINING);
    CHECK(prepared());w.arena.driver[FX_INJECT]=FX_CLOCK_LOSS;tick(12);
    CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && (w.e.flags&HMS_EP_CLOCK_QUALIFIED)==0u);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u);return 1;
}
static int late_dispatch_and_limits(void){
    uint8_t p[66];
    CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);tick(12);tick(13);
    w.arena.driver[FX_INJECT]=FX_LATE|FX_IGNORE_CUTOFF;tick(14);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==1u && w.s.bytes[ST_LIFE]==ST_FAULT);
    CHECK((w.arena.record[0][40]&7u)==ST_RECORD_UNKNOWN);
    mutation_bytes(p,ST_ACKNOWLEDGE);p32(p+60,1);CHECK(call(p,66)==ST_ACK_PENDING);
    CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);tick(12);tick(13);
    w.arena.driver[FX_INJECT]=FX_LATE;tick(14);
    CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u && w.s.bytes[ST_LIFE]==ST_FAULT);
    CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);
    p32(w.s.bytes+ST_ACT,UINT32_MAX);p32(w.s.bytes+ST_ACK,UINT32_MAX);
    cycle(12);CHECK(w.s.bytes[ST_REASON+1]==ST_COUNTER && r32(w.arena.driver+FX_DISPATCHES)==0u);
    CHECK(prepared());p32(w.s.bytes+ST_MUT,UINT32_MAX);mutation_bytes(p,ST_STOP_OP);p32(p+44,UINT32_MAX);p16(p+64,ST_STOP);
    /* Same sequence with different retained body conflicts; no wrap/new work. */
    CHECK(call(p,66)==HMS_EP_CONFLICT && r32(w.s.bytes+ST_MUT)==UINT32_MAX);return 1;
}
static int prepared_expiry_and_revoke(void){
    uint8_t p[66],revoke[10];
    CHECK(opened());tick(1000);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_OWNED]==3u && r32(w.arena.driver+FX_DISPATCHES)==0u);
    tick(1001);tick(1002);CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && w.s.bytes[ST_OWNED]==3u);
    mutation_bytes(p,ST_STOP_OP);p16(p+64,ST_STOP);CHECK(call(p,66)==HMS_EP_OK && w.s.bytes[ST_LIFE]==ST_STOPPED);
    CHECK(prepared());memset(revoke,0,10);revoke[0]=2;revoke[1]=ST_REVOKE;p32(revoke+2,2);p16(revoke+6,1);p16(revoke+8,6);
    CHECK(call(revoke,10)==HMS_EP_OK && w.e.context_valid==0u && w.s.bytes[ST_LIFE]==ST_DRAINING);
    CHECK(w.s.bytes[ST_OWNED]==3u);mutation_bytes(p,ST_RENEW);p64(p+52,2000);CHECK(call(p,66)==HMS_EP_BAD_STATE);
    tick(3);tick(4);CHECK(w.s.bytes[ST_LIFE]==ST_STOPPED && w.s.bytes[ST_OWNED]==3u);return 1;
}
static int loss_witness_ordering(void){
    uint8_t p[66],q[49];unsigned mode;
    for(mode=0;mode<3u;++mode){
        CHECK(prepared());mutation_bytes(p,ST_SUSPEND_OP);p16(p+64,ST_SUSPEND);
        CHECK(call(p,66)==HMS_EP_OK);CHECK(r64(w.s.bytes+ST_LOSS_AT)==2u);
        tick(10);CHECK(w.s.bytes[ST_LOSS_COMMAND]==3u && r64(w.s.bytes+ST_QUIET_AT)==10u);
        memcpy(q,golden_open,44);q[1]=ST_STATUS;memset(q+44,0,5);
        CHECK(call(q,49)==HMS_EP_OK && r64(w.out+135)==UINT64_MAX);
        w.arena.driver[FX_WITNESS_TIME]=(uint8_t)mode;tick(11);
        CHECK(r64(w.s.bytes+ST_LOSS_AT)==2u && w.s.bytes[ST_OWNED]==3u);
        if(mode==0u){CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && r64(w.s.bytes+ST_QUIET_AT)==11u);}
        else{
            CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && w.s.bytes[ST_QUIET]==0u);
            CHECK(call(q,49)==HMS_EP_OK && r64(w.out+135)==UINT64_MAX);
        }
    }
    CHECK(prepared());mutation_bytes(p,ST_SUSPEND_OP);p16(p+64,ST_SUSPEND);CHECK(call(p,66)==HMS_EP_OK);
    w.arena.driver[FX_INJECT]=FX_LATE;tick(10);
    CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && r64(w.s.bytes+ST_QUIET_AT)==UINT64_MAX);
    CHECK(w.s.bytes[ST_LOSS_COMMAND]==4u && r32(w.arena.driver+FX_LOSSES)==0u);
    CHECK(prepared());mutation_bytes(p,ST_SUSPEND_OP);p16(p+64,ST_SUSPEND);CHECK(call(p,66)==HMS_EP_OK);
    tick(102);CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && r64(w.s.bytes+ST_QUIET_AT)==UINT64_MAX);
    CHECK(r32(w.arena.driver+FX_LOSSES)==0u);return 1;
}
static int acquisition_boundaries(void){
    uint8_t p[66];
    CHECK(opened());w.arena.driver[FX_INJECT]=FX_LATE;tick(0);
    CHECK(r32(w.arena.driver+FX_SEQUENCE)==0u && r32(w.arena.observation[0]+12)==0u);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_OWNED]==3u);
    CHECK(w.s.bytes[ST_REASON+1]==ST_LEASE_LOSS && r32(w.arena.driver+FX_DISPATCHES)==0u);
    CHECK(opened());w.arena.driver[FX_BOUNDARY_DRIFT]=1;tick(0);
    CHECK(r32(w.arena.driver+FX_SEQUENCE)==0u && r32(w.arena.observation[0]+12)==0u);
    CHECK(w.s.bytes[ST_REASON+1]==ST_EPOCH_LOSS && w.s.bytes[ST_OWNED]==3u);
    CHECK(opened());w.arena.driver[FX_BOUNDARY_DRIFT]=2;tick(0);
    CHECK(r32(w.arena.driver+FX_SEQUENCE)==0u && w.s.bytes[ST_LIFE]==ST_FAULT);
    CHECK(w.s.bytes[ST_OWNED]==3u && r32(w.arena.driver+FX_DISPATCHES)==0u);
    CHECK(prepared());mutation_bytes(p,ST_SUSPEND_OP);p16(p+64,ST_SUSPEND);CHECK(call(p,66)==HMS_EP_OK);
    tick(10);CHECK(w.s.bytes[ST_LOSS_COMMAND]==3u);
    w.arena.driver[FX_INJECT]=FX_LATE;tick(11);
    CHECK(r32(w.arena.driver+FX_SEQUENCE+4)==1u && w.s.bytes[ST_QUIET]==0u);
    CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && w.s.bytes[ST_OWNED]==3u);return 1;
}
static int interrupted_feedback_ack(void){
    uint8_t suspend[66],ack[66],retained[44];unsigned uncertain;
    for(uncertain=0;uncertain<2u;++uncertain){
        CHECK(prepared());p32(w.arena.driver+FX_DEMAND,35000);cycle(12);
        CHECK((w.arena.record[0][40]&7u)==ST_RECORD_PENDING && r32(w.arena.driver+FX_DISPATCHES)==1u);
        CHECK(call(golden_start,66)==HMS_EP_OK && r32(w.arena.driver+FX_DISPATCHES)==1u);
        mutation_bytes(suspend,ST_SUSPEND_OP);p16(suspend+64,ST_SUSPEND);CHECK(call(suspend,66)==HMS_EP_OK);
        memcpy(retained,w.arena.record[0],44);
        CHECK((retained[40]&7u)==ST_RECORD_INTERRUPTED && (retained[40]&8u)!=0u && ((retained[40]>>4)&3u)==HMS_EP_UNVERIFIED);
        mutation_bytes(ack,ST_ACKNOWLEDGE);p32(ack+60,1);CHECK(call(ack,66)==ST_ACK_PENDING);
        CHECK(w.s.bytes[ST_COUNT]==1u && w.s.bytes[ST_OWNED]==3u);
        if(uncertain!=0u)w.arena.driver[FX_BOUNDARY_DRIFT]=3;
        tick(15);mutation_bytes(ack,ST_ACKNOWLEDGE);p32(ack+60,1);CHECK(call(ack,66)==ST_ACK_PENDING);
        CHECK(r32(w.arena.driver+FX_LOSSES)==1u && w.s.bytes[ST_COUNT]==1u);
        CHECK(call(suspend,66)==HMS_EP_OK && r32(w.arena.driver+FX_LOSSES)==1u);
        if(uncertain!=0u){
            CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && w.s.bytes[ST_QUIET]==0u);
            CHECK((w.arena.record[0][40]&7u)==ST_RECORD_INTERRUPTED && (w.s.bytes[ST_FLAGS+1]&ST_UNRESOLVED)!=0u);
            CHECK(r64(w.s.bytes+ST_QUIET_AT)==UINT64_MAX);
        }else{
            tick(16);CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && w.s.bytes[ST_QUIET]==3u);
            mutation_bytes(ack,ST_ACKNOWLEDGE);p32(ack+60,1);CHECK(call(ack,66)==HMS_EP_OK);
            CHECK(w.s.bytes[ST_COUNT]==0u && w.s.bytes[ST_OWNED]==3u);
            CHECK((retained[40]&7u)==ST_RECORD_INTERRUPTED && ((retained[40]>>4)&3u)==HMS_EP_UNVERIFIED);
        }
    }
    return 1;
}
static int finite_interoperation(void){
    uint8_t p[134],call_packet[96],reference_packet[44];
    CHECK(full_ledger());mutation_bytes(p,ST_ACKNOWLEDGE);p32(p+60,2);CHECK(call(p,66)==HMS_EP_OK);
    mutation_bytes(p,ST_STOP_OP);p16(p+64,ST_STOP);CHECK(call(p,66)==HMS_EP_OK);
    mutation_bytes(p,ST_RETIRE);p32(p+60,2);CHECK(call(p,66)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_SLOT]==ST_EMPTY && w.e.operation_length==0u && r32(w.s.bytes+ST_HIGH)==1u);
    CHECK(call(p,66)==HMS_EP_OLD_OR_FORGOTTEN);
    memset(p,0,48);p[0]=1;p[1]=17;p32(p+2,2);p16(p+6,1);memset(p+8,0x55,32);p64(p+40,564);
    CHECK(call(p,48)==HMS_EP_OK);
    memset(call_packet,0,96);call_packet[0]=1;call_packet[1]=32;p32(call_packet+2,2);p16(call_packet+6,1);
    p32(call_packet+8,1);memset(call_packet+12,0x22,32);p16(call_packet+44,1);call_packet[46]=3;
    p64(call_packet+52,64);p64(call_packet+60,84);p64(call_packet+68,114);p32(call_packet+76,100);p64(call_packet+80,564);
    p32(call_packet+88,2);p32(call_packet+92,2);CHECK(call(call_packet,96)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_SLOT]==ST_FINITE && r32(w.s.bytes+ST_HIGH)==1u);
    memcpy(p,golden_open,134);p32(p+8,2);CHECK(call(p,134)==HMS_EP_BUSY);
    tick(65);tick(67);CHECK(w.e.receipt.execution==HMS_EP_COMPLETED && w.e.receipt.held_mask==0u);
    memcpy(reference_packet,call_packet,44);reference_packet[1]=35;CHECK(call(reference_packet,44)==HMS_EP_OK);
    CHECK(w.s.bytes[ST_SLOT]==ST_EMPTY && w.e.call_high_water==1u && r32(w.s.bytes+ST_HIGH)==1u);
    CHECK(call(golden_open,134)==HMS_EP_OLD_OR_FORGOTTEN);
    memcpy(p,golden_open,134);p32(p+8,2);p32(p+80,3);p32(p+84,3);CHECK(call(p,134)==HMS_EP_OK);
    CHECK(r32(w.s.bytes+ST_HIGH)==2u && w.e.call_high_water==1u);return 1;
}
static size_t frame_request(const uint8_t *payload,uint16_t length,uint8_t *wire){
    uint8_t raw[HMS_FRAME_RAW];uint16_t crc=0xffffu,i;size_t n=0;
    memset(raw,0,sizeof(raw));raw[0]='H';raw[1]='M';raw[2]=1;raw[3]=1;
    p64(raw+6,1);p32(raw+14,99);p16(raw+18,length);memcpy(raw+20,payload,length);
    for(i=0;i<(uint16_t)(20u+length);++i){
        uint8_t bit;crc^=raw[i];for(bit=0;bit<8u;++bit)crc=(uint16_t)((crc>>1)^((crc&1u)!=0u?0x8408u:0u));
    }
    crc^=0xffffu;raw[20u+length]=(uint8_t)crc;raw[21u+length]=(uint8_t)(crc>>8);
    wire[n++]=0x7e;
    for(i=0;i<(uint16_t)(22u+length);++i){
        if(raw[i]==0x7eu || raw[i]==0x7du){wire[n++]=0x7d;wire[n++]=(uint8_t)(raw[i]^0x20u);}
        else wire[n++]=raw[i];
    }
    wire[n++]=0x7e;return n;
}
static int stop_backpressure(void){
    uint8_t p[66],wire[500],byte;size_t n,i;uint8_t saved[HMS_FRAME_RAW];
    CHECK(prepared());mutation_bytes(p,ST_STOP_OP);p16(p+64,ST_STOP);
    /* Independent bounded framing helper; the actual parser/link handles it. */
    n=frame_request(p,66,wire);CHECK(n<=sizeof(wire));
    w.link.transmit_phase=2;w.link.transmit_length=4;w.link.transmit_index=1;
    memset(w.link.transmit,0xa5,sizeof(w.link.transmit));memcpy(saved,w.link.transmit,sizeof(saved));
    for(i=0;i<n;++i)hms_endpoint_link_feed(&w.link,&w.e,wire[i],2,25);
    CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_OWNED]==3u);
    CHECK(w.link.transmit_phase==2u && w.link.transmit_index==1u && memcmp(saved,w.link.transmit,sizeof(saved))==0);
    CHECK(hms_endpoint_link_next(&w.link,&byte)==1u && byte==0xa5u);
    tick(3);tick(4);CHECK(w.s.bytes[ST_LIFE]==ST_STOPPED);return 1;
}
int main(void){
    static int (*const cases[])(void)={wire_and_refusals,replay_and_renewal,encoded_time_boundaries,ledger_ack_resume,
        pending_ack_and_feedback,feedback_signed_range,source_and_clock_faults,late_dispatch_and_limits,
        prepared_expiry_and_revoke,loss_witness_ordering,acquisition_boundaries,interrupted_feedback_ack,finite_interoperation,stop_backpressure};
    unsigned i;
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);++i)if(cases[i]()==0)return 1;
    printf("{\"cases\":%u,\"assertions\":%u,\"physical_qualification\":false}\n",i,assertions);return 0;
}
