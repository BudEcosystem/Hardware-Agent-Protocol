#include "endpoint_fixture.h"
#include "../protocol/endpoint/link.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static hms_endpoint e;
static hms_endpoint_fixture f;
static hms_ep_config c;
static uint8_t request_bytes[193], response[192];
static uint16_t flags, response_length;
static uint64_t now;
static uint32_t sequence;
static unsigned assertions, cases;
#define CHECK(condition) do { ++assertions; if (!(condition)) { fprintf(stderr, "check failed line %d: %s\n", __LINE__, #condition); exit(1); } } while (0)
#define CASE(name) do { name(); ++cases; } while (0)

static void p16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)(v>>8); p[1]=(uint8_t)v; }
static void p32(uint8_t *p, uint32_t v) { uint8_t i; for(i=0;i<4u;++i){p[3u-i]=(uint8_t)v;v>>=8;} }
static void p64(uint8_t *p, uint64_t v) { uint8_t i; for(i=0;i<8u;++i){p[7u-i]=(uint8_t)v;v>>=8;} }
static uint64_t g64(const uint8_t *p) { uint8_t i;uint64_t v=0;for(i=0;i<8u;++i)v=(v<<8)|p[i];return v; }
static uint8_t send_session(uint16_t length, uint64_t session) {
    f.clock_tick=now; f.platform_flags=flags;
    CHECK(hms_endpoint_handle(&e,1,0,session,++sequence,request_bytes,length,now,flags,response,&response_length)==1u);
    return response[6];
}
static uint8_t send(uint16_t length) { return send_session(length,42); }
static void tick(uint64_t time) {
    now=time; f.clock_tick=now; f.platform_flags=flags;
    hms_endpoint_poll(&e,now,flags); now=f.clock_tick;
}
static void bind(uint32_t expected, uint16_t handle) {
    uint8_t i;
    memset(request_bytes,0,sizeof(request_bytes));request_bytes[0]=1;request_bytes[1]=16;
    p32(request_bytes+2,expected);p16(request_bytes+6,handle);
    for(i=0;i<32u;++i){request_bytes[8u+i]=c.constant_byte(c.user,HMS_EP_MANIFEST,i);request_bytes[40u+i]=(uint8_t)(0x40u+i);}
}
static void arm(uint32_t generation, uint16_t handle, uint64_t until) {
    uint8_t i;
    memset(request_bytes,0,sizeof(request_bytes));request_bytes[0]=1;request_bytes[1]=17;
    p32(request_bytes+2,generation);p16(request_bytes+6,handle);
    for(i=0;i<32u;++i)request_bytes[8u+i]=(uint8_t)(0x40u+i);
    p64(request_bytes+40,until);
}
static void setup_mode(uint16_t mode) {
    hms_endpoint_fixture_init(&f,&c);now=1000;flags=mode;sequence=0;
    f.platform_flags=flags;f.clock_tick=now;
    CHECK(hms_endpoint_init(&e,&c,42,now,flags)==1u);
    bind(1,7);CHECK(send(72)==0u);arm(2,7,2000);CHECK(send(48)==0u);
}
static void setup(void) { setup_mode(HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_SIMULATOR_ONLY); }
static void op(uint32_t call, uint32_t first_fence, uint32_t second_fence) {
    uint8_t i;
    memset(request_bytes,0,sizeof(request_bytes));request_bytes[0]=1;request_bytes[1]=32;
    p32(request_bytes+2,2);p16(request_bytes+6,7);p32(request_bytes+8,call);
    for(i=0;i<32u;++i)request_bytes[12u+i]=(uint8_t)(0x60u+i);
    p16(request_bytes+44,0x1234);request_bytes[46]=5;request_bytes[47]=8;
    p64(request_bytes+52,1100);p64(request_bytes+60,1200);p64(request_bytes+68,1500);
    p32(request_bytes+76,200);p64(request_bytes+80,1600);
    p32(request_bytes+88,first_fence);p32(request_bytes+92,second_fence);
    p32(request_bytes+96,1000);p32(request_bytes+100,UINT32_C(0xffffffe7));
}
static void ref(uint8_t opcode, uint32_t call) {
    uint8_t i;
    memset(request_bytes,0,sizeof(request_bytes));request_bytes[0]=1;request_bytes[1]=opcode;
    p32(request_bytes+2,2);p16(request_bytes+6,7);p32(request_bytes+8,call);
    for(i=0;i<32u;++i)request_bytes[12u+i]=(uint8_t)(0x60u+i);
}
static void revoke(void) {
    memset(request_bytes,0,sizeof(request_bytes));request_bytes[0]=1;request_bytes[1]=18;
    p32(request_bytes+2,2);p16(request_bytes+6,7);p16(request_bytes+8,6);
}
static void empty_admission(void) {
    uint8_t i;
    CHECK(e.operation_length==0u);CHECK(e.call_high_water==0u);CHECK(f.dispatches==0u);CHECK(f.effects==0u);
    for(i=0;i<8u;++i)CHECK(e.fence_floor[i]==0u);
}

static void lifecycle_and_exact_replay(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);CHECK(e.receipt.execution==HMS_EP_QUEUED);
    CHECK(send(104)==0u);CHECK(f.dispatches==0u);CHECK(e.receipt.revision==1u);
    request_bytes[99]^=1;CHECK(send(104)==HMS_EP_CONFLICT);CHECK(e.call_high_water==1u);
    tick(1150);CHECK(f.dispatches==1u);CHECK(e.receipt.may_have_acted==1u);
    op(1,5,9);CHECK(send(104)==0u);CHECK(f.dispatches==1u);
    tick(1300);CHECK(e.receipt.execution==HMS_EP_COMPLETED);CHECK(f.effects==1u);CHECK(e.receipt.held_mask==5u);
    ref(35,1);CHECK(send(44)==HMS_EP_BUSY);tick(1300);CHECK(e.receipt.held_mask==0u);
    ref(33,1);CHECK(send(44)==0u);CHECK(response_length==90u);CHECK(response[89]==0xcfu);
    ref(35,1);CHECK(send(44)==0u);CHECK(e.operation_length==0u);CHECK(e.call_high_water==1u);
    CHECK(e.fence_floor[0]==5u&&e.fence_floor[2]==9u);
    ref(33,1);CHECK(send(44)==HMS_EP_OLD_OR_FORGOTTEN);
    op(1,5,9);CHECK(send(104)==HMS_EP_OLD_OR_FORGOTTEN);CHECK(f.effects==1u);
}
static void retained_receipt_excludes_new_call(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);tick(1300);tick(1300);
    op(2,6,10);p64(request_bytes+60,1400);CHECK(send(104)==HMS_EP_BUSY);CHECK(e.call_high_water==1u);
}
static void all_prefixes_and_reserved_fields(void) {
    uint16_t length;
    for(length=0;length<104u;++length){
        uint8_t emitted;
        setup();op(1,5,9);f.clock_tick=now;f.platform_flags=flags;
        emitted=hms_endpoint_handle(&e,1,0,42,3,request_bytes,length,now,flags,response,&response_length);
        if(length<2u)CHECK(emitted==0u);else{CHECK(emitted==1u);CHECK(response[6]==HMS_EP_BAD_LENGTH);}
        empty_admission();
    }
    setup();op(1,5,9);request_bytes[49]=1;CHECK(send(104)==HMS_EP_RESERVED);empty_admission();
    op(1,5,9);request_bytes[50]=1;CHECK(send(104)==HMS_EP_RESERVED);empty_admission();
    op(1,5,9);request_bytes[47]=73;CHECK(send(104)==HMS_EP_BAD_LENGTH);empty_admission();
    op(0,5,9);CHECK(send(104)==HMS_EP_BAD_ARGUMENT);empty_admission();
    op(1,5,9);CHECK(send_session(104,41)==HMS_EP_BOOT_MISMATCH);empty_admission();
}
static void no_partial_fence_admission(void) {
    setup();e.fence_floor[2]=9;op(1,5,9);CHECK(send(104)==HMS_EP_STALE_FENCE);
    CHECK(e.fence_floor[0]==0u);CHECK(e.fence_floor[2]==9u);CHECK(e.operation_length==0u);
    op(1,5,10);p32(request_bytes+96,100001);CHECK(send(104)==HMS_EP_BAD_ARGUMENT);CHECK(e.fence_floor[0]==0u);
}
static void future_cancel_is_not_tombstone(void) {
    setup();ref(34,1);CHECK(send(44)==HMS_EP_NOT_SEEN);CHECK(e.call_high_water==0u);
    op(1,5,9);CHECK(send(104)==0u);tick(1150);CHECK(f.dispatches==1u);
}
static void queued_cancel_and_expiry(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);ref(34,1);CHECK(send(44)==0u);
    CHECK(e.receipt.execution==HMS_EP_CANCELED&&e.receipt.cancellation==HMS_EP_CANCEL_CONFIRMED);
    CHECK(e.receipt.may_have_acted==0u&&e.receipt.held_mask==0u);tick(1150);CHECK(f.dispatches==0u);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1200);CHECK(e.receipt.execution==HMS_EP_REJECTED);
    CHECK(e.receipt.reason==1u&&e.receipt.held_mask==0u&&f.dispatches==0u);
}
static void cancellation_races(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);ref(34,1);CHECK(send(44)==0u);
    CHECK(e.receipt.cancellation==HMS_EP_CANCEL_REQUESTED);CHECK(e.receipt.held_mask==5u);
    tick(1150);CHECK(e.receipt.execution==HMS_EP_CANCELED);CHECK(e.receipt.held_mask==5u);
    tick(1150);CHECK(e.receipt.held_mask==0u&&f.effects==0u);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);f.mode=HMS_FIXTURE_COMPLETE_ON_CANCEL;
    ref(34,1);CHECK(send(44)==0u);tick(1300);CHECK(e.receipt.execution==HMS_EP_COMPLETED);
    CHECK(e.receipt.cancellation==HMS_EP_CANCEL_ACK&&f.effects==1u);
    ref(34,1);CHECK(send(44)==0u);CHECK(e.receipt.execution==HMS_EP_COMPLETED);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);f.mode=HMS_FIXTURE_REJECT_CANCEL;
    ref(34,1);CHECK(send(44)==0u);tick(1150);CHECK(e.receipt.cancellation==HMS_EP_CANCEL_REJECTED);
    tick(1300);CHECK(e.receipt.execution==HMS_EP_COMPLETED);
}
static void immutable_operation_cutoff(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);
    arm(2,7,2500);CHECK(send(48)==0u);CHECK(e.armed_until==2500u);CHECK(g64(e.operation+80)==1600u);
    f.mode=HMS_FIXTURE_NEVER_COMPLETE;tick(1350);CHECK(e.receipt.execution==HMS_EP_FAILED);
    CHECK(e.receipt.reason==2u&&e.receipt.held_mask==5u&&f.effects==0u);
    tick(1350);CHECK(e.receipt.held_mask==0u);
}
static void slow_admission_and_start_guards(void) {
    setup();f.guard_advance_ms=200;op(1,5,9);CHECK(send(104)==HMS_EP_START_EXPIRED);empty_admission();
    setup();op(1,5,9);CHECK(send(104)==0u);f.guard_advance_ms=60;tick(1150);
    CHECK(e.receipt.execution==HMS_EP_REJECTED&&e.receipt.reason==1u);CHECK(f.dispatches==0u);
}
static void callback_crosses_cutoff_without_backdating(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);f.mode=HMS_FIXTURE_LATE_CALLBACK;tick(1340);
    CHECK(e.now_tick==1360u);CHECK(e.receipt.execution==HMS_EP_UNKNOWN);CHECK(e.receipt.reason==2u);
    CHECK(e.receipt.held_mask==5u&&e.receipt.result_length==0u&&f.effects==1u);
    CHECK(e.state==HMS_EP_FAULT&&(e.flags&HMS_EP_INHIBITED)!=0u);
}
static void revocation_rebind_and_floors(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);revoke();CHECK(send(10)==0u);
    CHECK(e.control_generation==3u&&e.context_valid==0u&&e.receipt.held_mask==5u);
    arm(3,7,2200);CHECK(send(48)==HMS_EP_BAD_STATE);
    ref(33,1);CHECK(send(44)==0u);tick(1150);tick(1150);CHECK(e.state==HMS_EP_RESET);
    ref(35,1);CHECK(send(44)==0u);bind(3,8);CHECK(send(72)==0u);CHECK(e.control_generation==4u);
    arm(4,8,2200);CHECK(send(48)==0u);revoke();p32(request_bytes+2,4);CHECK(send(10)==HMS_EP_CONTEXT_MISMATCH);
    CHECK(e.control_generation==4u&&e.state==HMS_EP_ARMED);
    op(2,5,10);p32(request_bytes+2,4);p16(request_bytes+6,8);CHECK(send(104)==HMS_EP_STALE_FENCE);
}
static void restart_unknown_and_old_boot_refusal(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);CHECK(f.dispatches==1u);
    flags|=HMS_EP_RECONCILE;f.platform_flags=flags;f.clock_tick=1000;now=1000;
    CHECK(hms_endpoint_init(&e,&c,43,now,flags)==1u);CHECK(e.operation_length==0u);
    op(1,5,9);CHECK(send(104)==HMS_EP_BOOT_MISMATCH);CHECK((e.flags&HMS_EP_INHIBITED)!=0u);
    bind(1,7);CHECK(send_session(72,43)==HMS_EP_RECONCILIATION_REQUIRED);CHECK(f.dispatches==1u);
}
static void clock_regression_and_invalid_initial_flags(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);tick(1140);
    CHECK(e.state==HMS_EP_FAULT&&(e.flags&HMS_EP_INHIBITED)!=0u);
    CHECK((e.flags&HMS_EP_CLOCK_QUALIFIED)==0u&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT&&e.receipt.reason==7u);
    tick(1300);CHECK((e.flags&HMS_EP_CLOCK_QUALIFIED)==0u);CHECK(e.now_tick==1150u);
    hms_endpoint_fixture_init(&f,&c);CHECK(hms_endpoint_init(&e,&c,42,1000,UINT16_C(0x8019))==1u);
    CHECK(e.state==HMS_EP_FAULT&&(e.flags&HMS_EP_INHIBITED)!=0u);
}
static void unknown_then_failed(void *user,uint8_t phase,uint16_t primitive,const uint8_t *a,uint8_t n,uint64_t time,const hms_ep_step_limits *limits,hms_ep_report *r) {
    hms_endpoint_fixture *fixture=user;
    (void)phase;(void)primitive;(void)a;(void)n;(void)time;(void)limits;
    r->terminal_state=fixture->loss_steps++==0u?HMS_EP_UNKNOWN:HMS_EP_FAILED;r->evidence_kind=HMS_EP_SIMULATION;
}
static void canceled_on_loss(void *user,uint8_t phase,uint16_t primitive,const uint8_t *a,uint8_t n,uint64_t time,const hms_ep_step_limits *limits,hms_ep_report *r) {
    (void)user;(void)phase;(void)primitive;(void)a;(void)n;(void)time;(void)limits;
    r->terminal_state=HMS_EP_CANCELED;r->evidence_kind=HMS_EP_SIMULATION;
}
static void clock_reason_survives_unknown_and_cancellation(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);c.step=unknown_then_failed;tick(1140);
    CHECK(e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.reason==7u);tick(1150);
    CHECK(e.receipt.execution==HMS_EP_FAILED&&e.receipt.reason==7u&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);ref(34,1);CHECK(send(44)==0u);c.step=canceled_on_loss;tick(1140);
    CHECK(e.receipt.execution==HMS_EP_CANCELED&&e.receipt.reason==7u&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);revoke();CHECK(send(10)==0u);tick(1140);
    CHECK(e.receipt.reason==7u&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT);
}
static void mode_flip_excludes_and_drains(void) {
    setup_mode(HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_PHYSICAL_COMMISSIONED);
    op(1,5,9);CHECK(send(104)==0u);flags=HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_SIMULATOR_ONLY;tick(1150);
    CHECK(f.dispatches==0u&&e.context_valid==0u&&e.control_generation==3u&&e.receipt.execution==HMS_EP_REJECTED);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);
    flags=HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_PHYSICAL_COMMISSIONED;tick(1151);
    CHECK(e.control_generation==3u&&e.context_valid==0u&&e.receipt.held_mask==5u);
    CHECK(e.receipt.execution==HMS_EP_FAILED&&f.effects==0u);
}
static void evidence_and_result_fail_closed(void) {
    uint8_t mode;
    for(mode=HMS_FIXTURE_FALSE_PHYSICAL;mode<=HMS_FIXTURE_OVERSIZE_RESULT;++mode){
        setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);f.mode=mode;tick(1300);
        CHECK(e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.held_mask==5u);CHECK(e.receipt.verification!=HMS_EP_VERIFIED);
    }
    setup_mode(HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_PHYSICAL_COMMISSIONED);
    op(1,5,9);CHECK(send(104)==0u);tick(1150);tick(1300);CHECK(e.receipt.execution==HMS_EP_UNKNOWN);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);f.mode=HMS_FIXTURE_EARLY_QUIESCENCE;tick(1151);
    CHECK(e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.held_mask==5u);
}
static void disputed_terminal_keeps_remaining_claims(void) {
    void (*original)(void *,uint8_t,uint16_t,const uint8_t *,uint8_t,uint64_t,const hms_ep_step_limits *,hms_ep_report *);
    setup();original=c.step;op(1,5,9);CHECK(send(104)==0u);tick(1150);tick(1300);
    CHECK(e.receipt.execution==HMS_EP_COMPLETED&&e.receipt.held_mask==5u);
    c.step=unknown_then_failed;tick(1300);CHECK(e.receipt.execution==HMS_EP_COMPLETED&&e.receipt.verification==HMS_EP_DISPUTED);
    c.step=original;tick(1300);CHECK(e.receipt.held_mask==5u);ref(35,1);CHECK(send(44)==HMS_EP_BUSY);
}
static void disputed_completion(void *user,uint8_t phase,uint16_t primitive,const uint8_t *a,uint8_t n,uint64_t time,const hms_ep_step_limits *limits,hms_ep_report *r) {
    (void)user;(void)phase;(void)primitive;(void)a;(void)n;(void)time;(void)limits;
    r->terminal_state=HMS_EP_COMPLETED;r->evidence_kind=HMS_EP_SIMULATION;r->verification=HMS_EP_DISPUTED;
    r->result_length=4;p32(r->result,975);r->quiescent_mask=5;
}
static void same_report_dispute_cannot_release_claims(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);c.step=disputed_completion;tick(1300);
    CHECK(e.receipt.execution==HMS_EP_COMPLETED&&e.receipt.verification==HMS_EP_DISPUTED);
    CHECK(e.receipt.held_mask==5u&&e.state==HMS_EP_FAULT);ref(35,1);CHECK(send(44)==HMS_EP_BUSY);
}
static uint8_t accepts_zero(void *user,uint16_t primitive,const uint8_t *a,uint8_t n,hms_ep_primitive *d) {
    hms_endpoint_fixture *fixture=user;(void)primitive;(void)a;(void)n;++fixture->loss_steps;
    d->resource_mask=5;d->max_run_ms=200;d->cancel_supported=1;d->result_length=4;
    d->completion_evidence_mask=(uint8_t)(1u<<HMS_EP_SIMULATION);return 0;
}
static void zero_primitive_is_not_delegated_to_driver(void) {
    setup();c.describe=accepts_zero;op(1,5,9);p16(request_bytes+44,0);CHECK(send(104)==HMS_EP_UNKNOWN_PRIMITIVE);
    CHECK(f.loss_steps==0u);empty_admission();
}
static void predicate_and_fence_checked_before_steps(void) {
    setup();op(1,5,9);CHECK(send(104)==0u);f.guard_denied=1;tick(1150);CHECK(f.dispatches==0u&&e.receipt.reason==10u);
    setup();op(1,5,9);CHECK(send(104)==0u);e.fence_floor[0]=6;tick(1150);CHECK(f.dispatches==0u&&e.receipt.reason==6u);
    setup();op(1,5,9);CHECK(send(104)==0u);tick(1150);e.fence_floor[0]=6;tick(1151);
    CHECK(e.receipt.execution==HMS_EP_FAILED&&e.receipt.held_mask==5u&&f.effects==0u);
}
static void exhaustion_never_wraps(void) {
    setup();e.control_generation=UINT32_MAX;revoke();p32(request_bytes+2,UINT32_MAX);CHECK(send(10)==HMS_EP_COUNTER_EXHAUSTED);
    CHECK(e.control_generation==UINT32_MAX&&e.state==HMS_EP_FAULT&&(e.flags&HMS_EP_INHIBITED)!=0u);
    setup();e.fence_floor[0]=UINT32_MAX;op(1,UINT32_MAX,9);CHECK(send(104)==HMS_EP_STALE_FENCE);CHECK(e.fence_floor[0]==UINT32_MAX);
    setup();e.call_high_water=UINT32_MAX;op(1,5,9);CHECK(send(104)==HMS_EP_OLD_OR_FORGOTTEN);CHECK(e.call_high_water==UINT32_MAX);
    setup();e.response_sequence=UINT32_MAX;op(1,5,9);
    CHECK(hms_endpoint_handle(&e,1,0,42,3,request_bytes,104,now,flags,response,&response_length)==0u);
    CHECK(e.operation_length==0u&&e.response_sequence==UINT32_MAX&&e.state==HMS_EP_FAULT);
}
static void maximum_payload_and_64bit_time(void) {
    uint8_t i;uint64_t base=UINT64_C(0x100000000);
    setup();now=base+1000;arm(2,7,base+2000);CHECK(send(48)==0u);
    op(1,5,9);p16(request_bytes+44,0x4242);request_bytes[46]=255;request_bytes[47]=72;
    p64(request_bytes+52,base+1100);p64(request_bytes+60,base+1200);p64(request_bytes+68,base+1500);p64(request_bytes+80,base+1600);
    for(i=0;i<8u;++i)p32(request_bytes+88u+(uint16_t)i*4u,1);
    for(i=0;i<72u;++i)request_bytes[120u+i]=i;
    CHECK(send(192)==0u);tick(base+1150);tick(base+1300);CHECK(e.receipt.execution==HMS_EP_COMPLETED);
    ref(33,1);CHECK(send(44)==0u);CHECK(response_length==118u&&response[117]==31u);
    CHECK(e.receipt.started_at==base+1150&&e.receipt.terminal_at==base+1300);
}
static uint16_t crc(const uint8_t *p,uint16_t n){uint16_t v=0xffff,i;for(i=0;i<n;++i){uint8_t j;v^=p[i];for(j=0;j<8u;++j)v=(uint16_t)((v>>1)^((v&1u)!=0u?0x8408u:0u));}return(uint16_t)(v^0xffffu);}
static void feed_frame(hms_endpoint_link *l,uint16_t length){
    uint8_t raw[214];uint16_t i,check;
    memset(raw,0,20);raw[0]='H';raw[1]='M';raw[2]=1;raw[3]=1;p64(raw+6,request_bytes[1]==1u?0u:42u);p32(raw+14,++sequence);p16(raw+18,length);
    memcpy(raw+20,request_bytes,length);check=crc(raw,(uint16_t)(20u+length));raw[20u+length]=(uint8_t)check;raw[21u+length]=(uint8_t)(check>>8);
    hms_endpoint_link_feed(l,&e,0x7e,now,flags);
    for(i=0;i<22u+length;++i){if(raw[i]==0x7e||raw[i]==0x7d){hms_endpoint_link_feed(l,&e,0x7d,now,flags);hms_endpoint_link_feed(l,&e,(uint8_t)(raw[i]^0x20u),now,flags);}else hms_endpoint_link_feed(l,&e,raw[i],now,flags);}
    hms_endpoint_link_feed(l,&e,0x7e,now,flags);
}
static void serial_backpressure_keeps_control_and_partial_frame(void) {
    hms_endpoint_link l;hms_frame_parser decoder;uint8_t byte;unsigned ready=0,count=0;
    setup();hms_endpoint_link_init(&l);request_bytes[0]=1;request_bytes[1]=1;feed_frame(&l,2);
    hms_frame_reset(&decoder);
    while(count++<10u){CHECK(hms_endpoint_link_next(&l,&byte)==1u);CHECK(hms_frame_feed(&decoder,byte)==HMS_FRAME_NONE);}
    op(1,5,9);feed_frame(&l,104);CHECK(e.operation_length==0u);
    revoke();feed_frame(&l,10);CHECK(e.context_valid==0u&&e.control_generation==3u);
    while(hms_endpoint_link_next(&l,&byte)!=0u)if(hms_frame_feed(&decoder,byte)==HMS_FRAME_READY)++ready;
    CHECK(ready==1u&&decoder.raw[21]==0x81u);CHECK(e.state==HMS_EP_RESET);
    CHECK(decoder.raw[20u+125u]==HMS_EP_ARMED); /* Retained original snapshot, not a mixed response. */
}
static void receive_deadline_and_uart_reset_preserve_operation(void) {
    hms_endpoint_link l;uint8_t byte;
    setup();op(1,5,9);CHECK(send(104)==0u);hms_endpoint_link_init(&l);
    CHECK(hms_endpoint_link_set_receive_budget(&l,0)==0u);CHECK(hms_endpoint_link_set_receive_budget(&l,100)==1u);
    hms_endpoint_link_feed(&l,&e,0x7e,1000,flags);hms_endpoint_link_feed(&l,&e,'H',1000,flags);
    CHECK(l.receive_partial==1u);hms_endpoint_link_feed(&l,&e,'M',1099,flags);CHECK(l.parser.length==2u);
    hms_endpoint_link_check_deadline(&l,1100);CHECK(l.receive_partial==0u&&l.parser.active==0u);
    CHECK(e.receipt.execution==HMS_EP_QUEUED&&e.call_high_water==1u&&e.fence_floor[0]==5u);
    hms_endpoint_link_feed(&l,&e,0x7e,1100,flags);hms_endpoint_link_feed(&l,&e,0x7d,1100,flags);
    hms_endpoint_link_reset_receive(&l);CHECK(l.parser.active==0u);CHECK(e.operation_length==104u);
    request_bytes[0]=1;request_bytes[1]=1;feed_frame(&l,2);CHECK(l.transmit_phase!=0u);
    while(hms_endpoint_link_next(&l,&byte)!=0u){}
    CHECK(e.receipt.execution==HMS_EP_QUEUED&&f.dispatches==0u);
}
static uint8_t reentrant_guard(void *user,uint16_t primitive,const uint8_t *a,uint8_t n) {
    uint8_t hello[2]={1,1},reply[192];uint16_t reply_length;
    (void)user;(void)primitive;(void)a;(void)n;
    CHECK(hms_endpoint_handle(&e,1,0,0,0,hello,2,now,flags,reply,&reply_length)==0u);
    hms_endpoint_poll(&e,now,flags);return 0;
}
static void callbacks_cannot_reenter_dispatch(void) {
    setup();c.guard=reentrant_guard;op(1,5,9);CHECK(send(104)==0u);tick(1150);CHECK(f.dispatches==1u);
}
static void deterministic_malformed_stress(void) {
    uint32_t random=UINT32_C(0x71baf913);unsigned iteration;uint16_t length,i;
    setup();
    for(iteration=0;iteration<20000u;++iteration){
        random=random*UINT32_C(1664525)+UINT32_C(1013904223);length=(uint16_t)(random%193u);
        for(i=0;i<length;++i){random=random*UINT32_C(1664525)+UINT32_C(1013904223);request_bytes[i]=(uint8_t)(random>>24);}
        (void)hms_endpoint_handle(&e,1,0,42,++sequence,request_bytes,length,now,flags,response,&response_length);
    }
    CHECK(f.dispatches==0u&&f.effects==0u&&e.operation_length==0u);
}
int main(void) {
    CASE(lifecycle_and_exact_replay);CASE(retained_receipt_excludes_new_call);CASE(all_prefixes_and_reserved_fields);
    CASE(no_partial_fence_admission);CASE(future_cancel_is_not_tombstone);CASE(queued_cancel_and_expiry);
    CASE(cancellation_races);CASE(immutable_operation_cutoff);CASE(slow_admission_and_start_guards);
    CASE(callback_crosses_cutoff_without_backdating);CASE(revocation_rebind_and_floors);CASE(restart_unknown_and_old_boot_refusal);
    CASE(clock_regression_and_invalid_initial_flags);CASE(clock_reason_survives_unknown_and_cancellation);CASE(mode_flip_excludes_and_drains);
    CASE(evidence_and_result_fail_closed);CASE(disputed_terminal_keeps_remaining_claims);CASE(predicate_and_fence_checked_before_steps);
    CASE(same_report_dispute_cannot_release_claims);CASE(zero_primitive_is_not_delegated_to_driver);
    CASE(exhaustion_never_wraps);CASE(maximum_payload_and_64bit_time);CASE(serial_backpressure_keeps_control_and_partial_frame);
    CASE(receive_deadline_and_uart_reset_preserve_operation);
    CASE(callbacks_cannot_reenter_dispatch);CASE(deterministic_malformed_stress);
    printf("{\"cases\":%u,\"assertions\":%u,\"malformed_inputs\":20000,\"endpoint_size\":%zu,\"link_size\":%zu,\"fixture_size\":%zu,\"config_size\":%zu}\n",cases,assertions,sizeof(hms_endpoint),sizeof(hms_endpoint_link),sizeof(hms_endpoint_fixture),sizeof(hms_ep_config));
    return 0;
}
