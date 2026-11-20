/* One source is compiled against both frozen baseline and candidate cores.
 * It traces the unchanged14 standing controls and explicit finite boundaries.
 * Only two pointer representations are zeroed; no logical state is normalized. */
#if defined(HMS_EQ_BASELINE)
#include "../../originals/project/tests/standing_fixture.h"
#include "../../originals/project/protocol/endpoint/link.h"
#else
#include "standing_fixture.h"
#include "../protocol/endpoint/link.h"
#endif
#if !defined(HMS_EP_BYTE_BACKEND) || !defined(HMS_EQ_EXPECTED_BACKEND)
#error differential_build_must_declare_the_selected_backend
#endif
_Static_assert(HMS_EP_BYTE_BACKEND==HMS_EQ_EXPECTED_BACKEND,"differential backend selection");
uint8_t hms_phase_test_account(hms_standing *,uint8_t,uint64_t);
#include <stdio.h>
#include <string.h>

static void trace_fixture_init(hms_st_arena *,hms_ep_config *,hms_st_config *);
static uint8_t trace_handle(hms_endpoint *,uint8_t,uint8_t,uint64_t,uint32_t,
    const uint8_t *,uint16_t,uint64_t,uint16_t,uint8_t *,uint16_t *);
static void trace_poll(hms_endpoint *,uint64_t,uint16_t);
#define hms_st_fixture_init trace_fixture_init
#define hms_endpoint_handle trace_handle
#define hms_endpoint_poll trace_poll
#define main retained_standing_main
#if defined(HMS_EQ_BASELINE)
#include "../../originals/project/tests/standing_controls.c"
#else
#include "standing_controls.c"
#endif
#undef main
#undef hms_endpoint_poll
#undef hms_endpoint_handle
#undef hms_st_fixture_init

static hms_ep_config callbacks;
static hms_st_config standing_callbacks;
static uint32_t describe_advance,clock_advance,describes,guards,clocks;
static unsigned trace_records;
static uint8_t *rewrite_request;
static uint8_t rewrite_stage,sample_variant;
static uint64_t rewrite_nb,rewrite_latest,rewrite_complete,rewrite_lease;
static void rewrite_times(uint8_t stage) {
    if(rewrite_request!=NULL && rewrite_stage==stage){
        p64(rewrite_request+52,rewrite_nb);p64(rewrite_request+60,rewrite_latest);
        p64(rewrite_request+68,rewrite_complete);p64(rewrite_request+80,rewrite_lease);
        printf("C request-time-rewrite %u %llu %llu %llu %llu\n",(unsigned)stage,
            (unsigned long long)rewrite_nb,(unsigned long long)rewrite_latest,
            (unsigned long long)rewrite_complete,(unsigned long long)rewrite_lease);
    }
}
static void blob(const void *data,size_t length) {
    const uint8_t *p=data;size_t i;
    for(i=0;i<length;++i)printf("%02x",(unsigned)p[i]);
}
static void snapshot(const char *kind,const hms_endpoint *e) {
    hms_endpoint copy;
    ++trace_records;printf("S %u %s ",trace_records,kind);
    memcpy(&copy,e,sizeof(copy));
    memset(&copy.config,0,sizeof(copy.config));memset(&copy.standing,0,sizeof(copy.standing));
    blob(&copy,sizeof(copy));putchar(' ');
    blob(w.s.bytes,sizeof(w.s.bytes));putchar(' ');blob(&w.arena,sizeof(w.arena));putchar('\n');
}
static uint8_t trace_constant(void *u,uint8_t kind,uint8_t index) {
    uint8_t value=callbacks.constant_byte(u,kind,index);
    printf("C constant %u %u %u\n",(unsigned)kind,(unsigned)index,(unsigned)value);return value;
}
static uint8_t trace_describe(void *u,uint16_t id,const uint8_t *a,uint8_t n,hms_ep_primitive *out) {
    uint8_t value;++describes;
    printf("C describe-arguments %u %u ",(unsigned)id,(unsigned)n);blob(a,n);putchar('\n');
    p64((uint8_t *)u+FX_CLOCK,r64((uint8_t *)u+FX_CLOCK)+describe_advance);
    value=callbacks.describe(u,id,a,n,out);rewrite_times(1);
    printf("C describe %u %u %u %llu %lu %u %u %u %u\n",(unsigned)id,(unsigned)n,(unsigned)value,
        (unsigned long long)r64((uint8_t *)u+FX_CLOCK),(unsigned long)out->max_run_ms,
        (unsigned)out->resource_mask,(unsigned)out->completion_evidence_mask,
        (unsigned)out->cancel_supported,(unsigned)out->result_length);return value;
}
static uint8_t trace_guard(void *u,uint16_t id,const uint8_t *a,uint8_t n) {
    uint8_t value;++guards;
    printf("C finite-guard-arguments %u %u ",(unsigned)id,(unsigned)n);blob(a,n);putchar('\n');
    value=callbacks.guard(u,id,a,n);rewrite_times(2);
    printf("C finite-guard %u %u %u %llu\n",(unsigned)id,(unsigned)n,(unsigned)value,
        (unsigned long long)r64((uint8_t *)u+FX_CLOCK));return value;
}
static uint8_t trace_clock(void *u,uint64_t *now,uint16_t *flags) {
    uint8_t value;++clocks;
    p64((uint8_t *)u+FX_CLOCK,r64((uint8_t *)u+FX_CLOCK)+clock_advance);
    value=callbacks.sample_clock(u,now,flags);
    printf("C clock %u %llu %u\n",(unsigned)value,(unsigned long long)*now,(unsigned)*flags);return value;
}
static void trace_finite_step(void *u,uint8_t phase,uint16_t id,const uint8_t *a,uint8_t n,
        uint64_t now,const hms_ep_step_limits *limits,hms_ep_report *out) {
    printf("C finite-step-before %u %u %u %llu %llu %llu ",(unsigned)phase,(unsigned)id,(unsigned)n,
        (unsigned long long)now,(unsigned long long)limits->latest_start,(unsigned long long)limits->ordinary_until);
    blob(a,n);putchar('\n');
    snapshot("finite-step-before",&w.e);callbacks.step(u,phase,id,a,n,now,limits,out);
    printf("C finite-report ");blob(out,sizeof(*out));putchar('\n');snapshot("finite-step-after",&w.e);
}
static uint32_t trace_epoch(void *u,uint8_t channel) {
    uint32_t value=standing_callbacks.source_epoch(u,channel);
    printf("C epoch %u %lu\n",(unsigned)channel,(unsigned long)value);return value;
}
static uint8_t trace_standing_guard(void *u,const uint8_t *configuration,uint8_t initial) {
    uint8_t value;
    printf("C standing-guard-configuration %u ",(unsigned)initial);blob(configuration,32);putchar('\n');
    value=standing_callbacks.guard(u,configuration,initial);
    printf("C standing-guard %u %u %llu\n",(unsigned)initial,(unsigned)value,
        (unsigned long long)r64((uint8_t *)u+FX_CLOCK));return value;
}
static void trace_standing_step(void *u,const hms_standing *authority,uint8_t phase,uint8_t command,
        uint64_t now,uint64_t cutoff,uint8_t *report) {
    printf("C standing-step-before %u %u %llu %llu\n",(unsigned)phase,(unsigned)command,
        (unsigned long long)now,(unsigned long long)cutoff);
    snapshot("standing-step-before",&w.e);
    standing_callbacks.step(u,authority,phase,command,now,cutoff,report);
    if(sample_variant!=0u && phase==ST_ACQUIRE_DEMAND && report[0]==ST_REPORT_SAMPLE){
        const uint8_t *old=w.arena.observation[0];
        if(sample_variant==1u){report[2]=0;p64(report+20,UINT64_MAX);}
        else if(sample_variant==2u){p32(report+12,2);p64(report+20,UINT64_MAX);}
        else if(sample_variant==3u){p32(report+16,0);p64(report+20,UINT64_MAX);}
        else if(sample_variant==4u)p64(report+20,UINT64_MAX);
        else if(sample_variant==5u)p64(report+20,now+UINT64_C(0x100000000));
        else if(sample_variant==7u)p32(report+28,200001);
        else if(sample_variant==8u || sample_variant==9u){
            p32(report+16,r32(old+12));p64(report+20,r64(old+4));
            p32(report+28,r32(old)+(sample_variant==9u?1u:0u));
        }else if(sample_variant==10u)p64(report+20,r64(old+4)-1u);
        printf("C sample-variant %u\n",(unsigned)sample_variant);
    }
    printf("C standing-report ");blob(report,32);putchar('\n');snapshot("standing-step-after",&w.e);
}
static void trace_fixture_init(hms_st_arena *a,hms_ep_config *finite,hms_st_config *standing) {
    hms_st_fixture_init(a,finite,standing);callbacks=*finite;standing_callbacks=*standing;
    finite->constant_byte=trace_constant;finite->describe=trace_describe;finite->guard=trace_guard;
    finite->sample_clock=trace_clock;finite->step=trace_finite_step;
    standing->source_epoch=trace_epoch;standing->guard=trace_standing_guard;standing->step=trace_standing_step;
    describe_advance=clock_advance=describes=guards=clocks=0;
    rewrite_request=NULL;rewrite_stage=sample_variant=0;rewrite_nb=rewrite_latest=rewrite_complete=rewrite_lease=0;
}
static uint8_t trace_handle(hms_endpoint *e,uint8_t kind,uint8_t channel,uint64_t session,uint32_t sequence,
        const uint8_t *p,uint16_t n,uint64_t now,uint16_t flags,uint8_t *out,uint16_t *length) {
    uint8_t result=hms_endpoint_handle(e,kind,channel,session,sequence,p,n,now,flags,out,length);
    printf("A handle %u %lu %u %llu %u ",(unsigned)result,(unsigned long)sequence,(unsigned)n,
        (unsigned long long)now,(unsigned)flags);
    if(out!=NULL && result!=0u)blob(out,length!=NULL?*length:7u);
    putchar('\n');snapshot("handle",e);return result;
}
static void trace_poll(hms_endpoint *e,uint64_t now,uint16_t flags) {
    hms_endpoint_poll(e,now,flags);printf("A poll %llu %u\n",(unsigned long long)now,(unsigned)flags);
    snapshot("poll",e);
}
static int finite_callback_boundaries(void) {
    const uint64_t base=UINT64_C(0x81234567fffffff8);
    uint8_t arm[48],request[96],query[44];unsigned mode;
    for(mode=0;mode<6u;++mode){
        int expected_status;uint64_t after;
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);
        if(mode==0u){
            uint8_t hello[2]={1,1},describe[3]={2,ST_DESCRIBE,0};unsigned i;
            CHECK(trace_handle(&w.e,1,0,0,++w.request,hello,2,base,25,w.out,&w.length)==1u);
            CHECK(w.length==186u && w.out[6]==HMS_EP_OK && r32(w.out+87)==2u);
            CHECK(r64(w.out+133)==base && r64(w.out+141)==0u && r32(w.out+149)==0u);
            for(i=0;i<16u;++i)CHECK(w.out[7u+i]==0xa0u+i);
            for(i=0;i<32u;++i){CHECK(w.out[23u+i]==0xb0u+i);CHECK(w.out[55u+i]==0xc0u+i);}
            CHECK(call(describe,3)==HMS_EP_OK && w.length==146u && w.out[7]==0u);
            for(i=0;i<16u;++i)CHECK(w.out[66u+i]==0xa0u+i);
            for(i=0;i<32u;++i){CHECK(w.out[82u+i]==0xb0u+i);CHECK(w.out[114u+i]==0xc0u+i);}
            describe[2]=1;CHECK(call(describe,3)==HMS_EP_OK && w.length==182u && w.out[7]==1u);
            CHECK(r32(w.out+66)==2u && r64(w.out+104)==base && w.out[116]==ST_EMPTY);
            CHECK(r32(w.out+134)==1u && r32(w.out+138)==1u && r32(w.out+142)==0u && r32(w.out+146)==0u);
        }
        memset(arm,0,sizeof(arm));arm[0]=1;arm[1]=17;p32(arm+2,2);p16(arm+6,1);
        memset(arm+8,0x55,32);p64(arm+40,base+500u);CHECK(call(arm,48)==HMS_EP_OK);
        CHECK(w.length==69u && r64(w.out+48)==base && r64(w.out+56)==base+500u);
        memset(request,0,sizeof(request));request[0]=1;request[1]=32;
        p32(request+2,2);p16(request+6,1);p32(request+8,1);memset(request+12,0x22,32);
        p16(request+44,1);request[46]=3;
        p64(request+52,base+3u);p64(request+60,base+10u);p64(request+68,base+100u);
        p32(request+76,100);p64(request+80,base+300u);p32(request+88,1);p32(request+92,1);
        describes=guards=clocks=0;
        if(mode<3u){describe_advance=3;clock_advance=(uint32_t)(4u+mode);p32(w.arena.driver+FX_GUARD_ADVANCE,2);}
        else{describe_advance=12;clock_advance=0;p32(w.arena.driver+FX_GUARD_ADVANCE,0);}
        if(mode==4u)w.arena.driver[FX_DENY]=1;
        if(mode==5u)p64(request+68,UINT64_MAX);
        expected_status=mode==0u?HMS_EP_OK:(mode==4u?HMS_EP_BAD_STATE:(mode==5u?HMS_EP_BAD_TIME:HMS_EP_START_EXPIRED));
        CHECK(call(request,96)==expected_status);
        CHECK(describes==1u && guards==(mode==5u?0u:1u) && clocks==(mode<4u?1u:0u));
        after=mode<3u?base+9u+mode:(mode==3u?base+12u:base);
        CHECK(w.e.now_tick==after && r32(w.arena.driver+FX_DISPATCHES)==0u);
        if(mode==0u){
            CHECK(w.e.receipt.queued_at==base+9u && w.e.receipt.execution==HMS_EP_QUEUED);
            CHECK(w.e.call_high_water==1u && w.e.fence_floor[0]==1u && w.e.fence_floor[1]==1u);
            describe_advance=clock_advance=0;p32(w.arena.driver+FX_GUARD_ADVANCE,0);
            tick(base+9u);CHECK(w.e.receipt.started_at==base+9u && r32(w.arena.driver+FX_DISPATCHES)==1u);
            tick(base+11u);CHECK(w.e.receipt.execution==HMS_EP_COMPLETED && w.e.receipt.held_mask==0u);
            memcpy(query,request,44);query[1]=33;CHECK(call(query,44)==HMS_EP_OK && w.length==86u);
            CHECK(r64(w.out+61)==base+9u && r64(w.out+69)==base+9u && r64(w.out+77)==base+11u);
            CHECK(trace_handle(&w.e,1,0,1,++w.request,query,44,base+11u,25,NULL,&w.length)==1u && w.length==0u);
            CHECK(trace_handle(&w.e,1,0,1,++w.request,query,44,base+11u,25,w.out,NULL)==1u && w.out[6]==0u);
        }else{
            CHECK(w.e.operation_length==0u && w.e.receipt.held_mask==0u && w.e.call_high_water==0u);
            CHECK(w.e.fence_floor[0]==0u && w.e.fence_floor[1]==0u && w.s.bytes[ST_SLOT]==ST_EMPTY);
        }
    }
    return 1;
}
static int public_lease_boundaries(void) {
    const uint64_t base=UINT64_C(0x81234567fffffff8);
    uint8_t arm[48],request[96];unsigned mode;
    for(mode=0;mode<7u;++mode){
        uint64_t until;int expected_status;
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);
        until=mode==0u?base-1u:(mode==1u?base:(mode==2u?base+1u:
            (mode==3u?base+60000u:(mode==4u?base+60001u:UINT64_MAX))));
        memset(arm,0,sizeof(arm));arm[0]=1;arm[1]=17;p32(arm+2,2);p16(arm+6,1);
        memset(arm+8,0x55,32);p64(arm+40,until);if(mode==6u)arm[8]^=1u;
        expected_status=mode==2u || mode==3u?HMS_EP_OK:(mode==6u?HMS_EP_CONTEXT_MISMATCH:HMS_EP_LEASE_INVALID);
        describes=guards=clocks=0;CHECK(call(arm,48)==expected_status);
        CHECK(describes==0u && guards==0u && clocks==0u && w.e.now_tick==base);
        CHECK(w.e.armed_until==(expected_status==HMS_EP_OK?until:0u));
        CHECK(w.e.state==(expected_status==HMS_EP_OK?HMS_EP_ARMED:HMS_EP_BOUND));
        CHECK(w.e.operation_length==0u && w.e.receipt.held_mask==0u && w.e.call_high_water==0u);
        CHECK(w.e.fence_floor[0]==0u && w.e.fence_floor[1]==0u && r32(w.arena.driver+FX_DISPATCHES)==0u);
    }
    for(mode=0;mode<10u;++mode){
        uint64_t lease;int expected_status;
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);
        memset(arm,0,sizeof(arm));arm[0]=1;arm[1]=17;p32(arm+2,2);p16(arm+6,1);
        memset(arm+8,0x55,32);p64(arm+40,base+100u);CHECK(call(arm,48)==HMS_EP_OK);
        memset(request,0,sizeof(request));request[0]=1;request[1]=32;
        p32(request+2,2);p16(request+6,1);p32(request+8,1);memset(request+12,0x22,32);
        p16(request+44,1);request[46]=3;p64(request+52,base);p64(request+60,base+10u);
        p64(request+68,base+20u);p32(request+76,100);p32(request+88,1);p32(request+92,1);
        lease=mode==0u?base+19u:(mode==2u?base+100u:(mode==3u?base+101u:
            (mode==4u || mode==6u?base:(mode==5u || mode==9u?UINT64_MAX:base+20u))));
        p64(request+80,lease);describes=guards=clocks=0;
        expected_status=mode==1u || mode==2u?HMS_EP_OK:HMS_EP_LEASE_INVALID;
        if(mode==5u)expected_status=HMS_EP_BAD_TIME;
        if(mode==6u){p64(request+52,base-1u);p64(request+60,base);expected_status=HMS_EP_START_EXPIRED;}
        if(mode==7u){describe_advance=20;expected_status=HMS_EP_START_EXPIRED;}
        if(mode==8u){describe_advance=100;expected_status=HMS_EP_BAD_STATE;}
        if(mode==9u){p16(request+6,2);expected_status=HMS_EP_CONTEXT_MISMATCH;}
        CHECK(call(request,96)==expected_status);
        CHECK(describes==(mode==9u?0u:1u));
        CHECK(guards==((mode==1u || mode==2u || mode==7u || mode==8u)?1u:0u) && clocks==guards);
        CHECK(w.e.now_tick==(mode==7u?base+20u:(mode==8u?base+100u:base)));
        /* When valid lease expiry is crossed in a callback, latest-start is
         * crossed first; at ARM expiry BAD_STATE precedes both. No mutation of
         * endpoint storage is used to make a later error artificially reachable. */
        CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u);
        if(expected_status==HMS_EP_OK){
            CHECK(w.e.operation_length==96u && w.e.receipt.held_mask==3u && w.e.call_high_water==1u);
            CHECK(w.e.fence_floor[0]==1u && w.e.fence_floor[1]==1u && w.s.bytes[ST_SLOT]==ST_FINITE);
        }else{
            CHECK(w.e.operation_length==0u && w.e.receipt.held_mask==0u && w.e.call_high_water==0u);
            CHECK(w.e.fence_floor[0]==0u && w.e.fence_floor[1]==0u && w.s.bytes[ST_SLOT]==ST_EMPTY);
        }
    }
    return 1;
}
/* The request is a mutable test-owned buffer, separate from arguments and
 * endpoint storage. Metadata/guard rewrite only its time fields after entry
 * capture. Successful admission still copies the later request bytes, exactly
 * as the parent does; no ordinary I/O is run from that synthetic request. */
static int finite_capture_phases(void) {
    const uint64_t base=UINT64_C(0x81234567fffffff8);
    uint8_t arm[48],request[96];unsigned mode;
    for(mode=0;mode<4u;++mode){
        int status;
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);
        memset(arm,0,sizeof(arm));arm[0]=1;arm[1]=17;p32(arm+2,2);p16(arm+6,1);
        memset(arm+8,0x55,32);p64(arm+40,base+500u);CHECK(call(arm,48)==HMS_EP_OK);
        memset(request,0,sizeof(request));request[0]=1;request[1]=32;
        p32(request+2,2);p16(request+6,1);p32(request+8,1);memset(request+12,0x22,32);
        p16(request+44,1);request[46]=3;p64(request+52,base);p64(request+60,base+10u);
        p64(request+68,base+100u);p32(request+76,100);p64(request+80,base+300u);
        p32(request+88,1);p32(request+92,1);
        if(mode==1u)p64(request+60,base); /* Invalid capture is not repaired later. */
        rewrite_request=request;rewrite_stage=(uint8_t)(mode<2u?1u:2u);
        rewrite_nb=mode==1u || mode==3u?base:base+50u;
        rewrite_latest=mode==1u || mode==3u?base+50u:base;
        rewrite_complete=mode==1u || mode==3u?base+100u:UINT64_MAX;
        rewrite_lease=mode==1u || mode==3u?base+300u:UINT64_MAX;
        if(mode==3u)p32(w.arena.driver+FX_GUARD_ADVANCE,10);
        describes=guards=clocks=0;status=call(request,96);rewrite_request=NULL;
        CHECK(status==(mode==1u?HMS_EP_BAD_TIME:(mode==3u?HMS_EP_START_EXPIRED:HMS_EP_OK)));
        CHECK(describes==1u && guards==(mode==1u?0u:1u) && clocks==guards);
        CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u);
        if(status==HMS_EP_OK){
            CHECK(w.e.operation_length==96u && w.e.receipt.held_mask==3u);
            CHECK(w.e.fence_floor[0]==1u && w.e.fence_floor[1]==1u);
            CHECK(r64(w.e.operation+52)==base+50u && r64(w.e.operation+60)==base);
            CHECK(r64(w.e.operation+68)==UINT64_MAX && r64(w.e.operation+80)==UINT64_MAX);
            CHECK(w.e.receipt.queued_at==base && w.e.receipt.may_have_acted==0u);
        }else{
            CHECK(w.e.operation_length==0u && w.e.receipt.held_mask==0u && w.e.call_high_water==0u);
            CHECK(w.e.fence_floor[0]==0u && w.e.fence_floor[1]==0u);
        }
    }
    return 1;
}
static int standing_report_phases(void) {
    const uint64_t base=UINT64_C(0x81234567fffffff8);
    uint8_t request[134],saved[24];unsigned mode;
    for(mode=1;mode<=10u;++mode){
        uint16_t reason;
        CHECK(setup());p64(w.arena.driver+FX_CLOCK,base);memcpy(request,golden_open,134);
        p64(request+112,base+1000u);CHECK(call(request,134)==HMS_EP_OK);
        cycle(base);CHECK(call(golden_start,66)==HMS_EP_OK);
        memcpy(saved,w.arena.observation[0],24);sample_variant=(uint8_t)mode;tick(base+12u);sample_variant=0;
        CHECK(r32(w.arena.driver+FX_DISPATCHES)==0u && w.s.bytes[ST_OWNED]==3u);
        if(mode==6u || mode==8u){
            CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && w.s.bytes[ST_PHASE]==1u);
            if(mode==6u)CHECK(r32(w.arena.observation[0]+12)==2u && r64(w.arena.observation[0]+4)==base+12u);
            else CHECK(memcmp(saved,w.arena.observation[0],24)==0);
        }else{
            reason=(uint16_t)(mode==1u || mode==7u?ST_QUALITY:(mode==2u?ST_EPOCH_LOSS:(mode==3u || mode==9u?ST_GAP:ST_STALE)));
            CHECK(w.s.bytes[ST_LIFE]==ST_DRAINING && w.s.bytes[ST_REASON+1]==reason);
            CHECK(memcmp(saved,w.arena.observation[0],24)==0 && w.s.bytes[ST_QUIET]==0u);
        }
    }
    return 1;
}
static int private_account_phase(void) {
    const uint64_t base=UINT64_C(0x81234567fffffff8);unsigned mode;
    /* Direct private-phase access makes the commit-before-false branch
     * observable without fabricating an invalid driver handoff. This is not
     * a reachability claim for the current installed synthetic driver. */
    for(mode=0;mode<5u;++mode){
        uint64_t until;uint32_t initial;uint8_t result;
        CHECK(first_transition());p64(w.arena.work,base);w.controller.max_on_ms=20;
        initial=mode==3u?UINT32_MAX-1u:10u;p32(w.s.bytes+ST_ACCOUNT,initial);
        until=mode==0u?base+9u:(mode==1u?base+10u:(mode==2u?base-1u:(mode==3u?base+2u:base+10u)));
        snapshot("private-account-before",&w.e);
        result=hms_phase_test_account(&w.s,(uint8_t)(mode!=4u),until);
        printf("T private-account %u %u\n",mode,(unsigned)result);snapshot("private-account-after",&w.e);
        CHECK(result==(uint8_t)(mode==0u));
        CHECK(r32(w.s.bytes+ST_ACCOUNT)==(mode==0u?19u:(mode==1u?20u:initial)));
        CHECK(w.s.bytes[ST_LIFE]==ST_ACTIVE && w.s.bytes[ST_OWNED]==3u);
    }
    return 1;
}
static int loss_account_partial_state(void) {
    uint8_t request[66];unsigned mode;
    for(mode=0;mode<2u;++mode){
        CHECK(first_transition());w.controller.max_on_ms=UINT32_MAX;
        /* Seed only the bounded accounting counter near exhaustion; all
         * dispatch/loss/witness traffic below follows the real controller. */
        p32(w.s.bytes+ST_ACCOUNT,mode==0u?UINT32_MAX-13u:UINT32_MAX-14u);
        mutation_bytes(request,ST_SUSPEND_OP);p16(request+64,ST_SUSPEND);
        CHECK(call(request,66)==HMS_EP_OK);tick(27);tick(28);
        CHECK(r32(w.arena.driver+FX_LOSSES)==1u && w.arena.driver[FX_OUTPUT]==0u);
        CHECK(w.s.bytes[ST_WITNESS]==1u && w.s.bytes[ST_WITNESS+1]==1u);
        CHECK(r64(w.s.bytes+ST_WITNESS+8)==28u && r32(w.s.bytes+ST_WITNESS+16)==0u);
        if(mode==0u){
            CHECK(w.s.bytes[ST_LIFE]==ST_FAULT && w.s.bytes[ST_REASON+1]==ST_SUSPEND);
            CHECK((w.s.bytes[ST_FLAGS+1]&ST_WITNESS_VALID)==0u && w.s.bytes[ST_QUIET]==0u);
            CHECK(r32(w.s.bytes+ST_ACCOUNT)==UINT32_MAX-13u);
        }else{
            CHECK(w.s.bytes[ST_LIFE]==ST_SUSPENDED && w.s.bytes[ST_QUIET]==3u);
            CHECK((w.s.bytes[ST_FLAGS+1]&ST_WITNESS_VALID)!=0u && r32(w.s.bytes+ST_ACCOUNT)==UINT32_MAX);
        }
        CHECK(w.s.bytes[ST_OWNED]==3u && w.e.fence_floor[0]==1u && w.e.fence_floor[1]==1u);
    }
    return 1;
}
int main(void) {
    unsigned before;
    if(retained_standing_main()!=0)return 1;
    before=assertions;
    if(!finite_callback_boundaries() || !public_lease_boundaries() || !finite_capture_phases() ||
            !standing_report_phases() || !private_account_phase() || !loss_account_partial_state())return 1;
    printf("{\"equivalence_cases\":20,\"old_cases\":14,\"assertions\":%u,\"added_assertions\":%u,\"trace_records\":%u,\"physical_qualification\":false}\n",
        assertions,assertions-before,trace_records);return 0;
}
