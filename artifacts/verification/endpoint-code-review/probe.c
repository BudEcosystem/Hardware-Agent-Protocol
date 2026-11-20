#include "tests/endpoint_fixture.h"
#include "protocol/endpoint/link.h"
#include "vectors.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void (*original_step)(void*,uint8_t,uint16_t,const uint8_t*,uint8_t,uint64_t,const hms_ep_step_limits*,hms_ep_report*);
static unsigned loss_calls,quiescence_calls;
static uint8_t (*original_describe)(void*,uint16_t,const uint8_t*,uint8_t,hms_ep_primitive*);
static unsigned passed;
static void request(hms_endpoint *e,hms_endpoint_fixture*f,const uint8_t*p,unsigned n,uint32_t seq){
 uint8_t out[192];uint16_t len=0;assert(hms_endpoint_handle(e,1,0,42,seq,p,(uint16_t)n,f->clock_tick,f->platform_flags,out,&len));assert(len>=7);assert(out[6]==0);
}
static void init(hms_endpoint *e,hms_ep_config*c,hms_endpoint_fixture*f){
 hms_endpoint_fixture_init(f,c);assert(hms_endpoint_init(e,c,42,1000,f->platform_flags));request(e,f,bind_request,sizeof bind_request,1);request(e,f,arm_request,sizeof arm_request,2);
}
static void admit(hms_endpoint *e,hms_endpoint_fixture*f){request(e,f,op_scaled_pair,sizeof op_scaled_pair,3);assert(e->receipt.execution==HMS_EP_QUEUED);}
static void poll(hms_endpoint*e,hms_endpoint_fixture*f,uint64_t now,uint16_t flags){f->clock_tick=now;f->platform_flags=flags;hms_endpoint_poll(e,now,flags);}
static void pass(const char*name){++passed;printf("PASS %s\n",name);}
static void unknown_then_failed(void*u,uint8_t phase,uint16_t p,const uint8_t*a,uint8_t n,uint64_t now,const hms_ep_step_limits*l,hms_ep_report*r){
 if(phase==HMS_EP_LOSS_STEP){r->terminal_state=(++loss_calls==1)?HMS_EP_UNKNOWN:HMS_EP_FAILED;r->evidence_kind=HMS_EP_SIMULATION;return;}original_step(u,phase,p,a,n,now,l,r);
}
static void disputed_quiescence(void*u,uint8_t phase,uint16_t p,const uint8_t*a,uint8_t n,uint64_t now,const hms_ep_step_limits*l,hms_ep_report*r){
 if(phase==HMS_EP_QUIESCENCE_STEP){++quiescence_calls;r->quiescent_mask=quiescence_calls==1?2:5;return;}original_step(u,phase,p,a,n,now,l,r);
}
static void disputed_with_release(void*u,uint8_t phase,uint16_t p,const uint8_t*a,uint8_t n,uint64_t now,const hms_ep_step_limits*l,hms_ep_report*r){
 original_step(u,phase,p,a,n,now,l,r);if(r->terminal_state==HMS_EP_COMPLETED){r->verification=HMS_EP_DISPUTED;r->quiescent_mask=5;}if(phase==HMS_EP_QUIESCENCE_STEP)++quiescence_calls;
}
static void clock_loss_after_start(void*u,uint8_t phase,uint16_t p,const uint8_t*a,uint8_t n,uint64_t now,const hms_ep_step_limits*l,hms_ep_report*r){
 original_step(u,phase,p,a,n,now,l,r);if(phase==HMS_EP_START)((hms_endpoint_fixture*)u)->platform_flags&=(uint16_t)~HMS_EP_CLOCK_QUALIFIED;
}
static uint8_t describe_zero_alias(void*u,uint16_t p,const uint8_t*a,uint8_t n,hms_ep_primitive*d){return original_describe(u,p==0?0x1234:p,a,n,d);}
static void feed(hms_endpoint_link*l,hms_endpoint*e,hms_endpoint_fixture*f,const uint8_t*p,unsigned n,uint32_t seq){
 uint8_t raw[214];unsigned i,b;uint16_t crc=0xffff;
 memset(raw,0,sizeof raw);raw[0]='H';raw[1]='M';raw[2]=1;raw[3]=1;raw[13]=42;
 raw[14]=(uint8_t)(seq>>24);raw[15]=(uint8_t)(seq>>16);raw[16]=(uint8_t)(seq>>8);raw[17]=(uint8_t)seq;raw[18]=(uint8_t)(n>>8);raw[19]=(uint8_t)n;memcpy(raw+20,p,n);
 for(i=0;i<n+20;++i){crc^=raw[i];for(b=0;b<8;++b)crc=(uint16_t)((crc>>1)^((crc&1)?0x8408:0));}crc^=0xffff;raw[n+20]=(uint8_t)crc;raw[n+21]=(uint8_t)(crc>>8);
 hms_endpoint_link_feed(l,e,0x7e,f->clock_tick,f->platform_flags);for(i=0;i<n+22;++i){if(raw[i]==0x7e||raw[i]==0x7d){hms_endpoint_link_feed(l,e,0x7d,f->clock_tick,f->platform_flags);hms_endpoint_link_feed(l,e,(uint8_t)(raw[i]^0x20),f->clock_tick,f->platform_flags);}else hms_endpoint_link_feed(l,e,raw[i],f->clock_tick,f->platform_flags);}hms_endpoint_link_feed(l,e,0x7e,f->clock_tick,f->platform_flags);
}
int main(void){
 hms_endpoint e;hms_ep_config c;hms_endpoint_fixture f;hms_endpoint_link l;uint8_t ref[44],saved[214],op[sizeof op_scaled_pair];
 init(&e,&c,&f);admit(&e,&f);poll(&e,&f,1150,21);assert(f.dispatches==0&&e.context_valid==0&&e.receipt.execution==HMS_EP_REJECTED&&e.receipt.held_mask==0);pass("queued mode transition invalidates without dispatch");
 init(&e,&c,&f);admit(&e,&f);poll(&e,&f,1150,25);poll(&e,&f,1160,21);assert(f.dispatches==1&&f.loss_steps==1&&e.context_valid==0&&e.receipt.held_mask==5&&e.receipt.execution==HMS_EP_FAILED);pass("running mode transition drains with claims");
 init(&e,&c,&f);original_step=c.step;c.step=unknown_then_failed;loss_calls=0;admit(&e,&f);poll(&e,&f,1150,25);poll(&e,&f,1100,25);assert(e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.reason==7&&e.receipt.held_mask==5);poll(&e,&f,1151,25);assert(e.receipt.execution==HMS_EP_FAILED&&e.receipt.reason==7&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT&&e.receipt.held_mask==5);pass("clock fault reason survives UNKNOWN to FAILED");
 init(&e,&c,&f);admit(&e,&f);f.guard_advance_ms=50;poll(&e,&f,1150,25);assert(f.dispatches==0&&e.receipt.execution==HMS_EP_REJECTED&&e.receipt.reason==1&&e.receipt.may_have_acted==0);pass("guard crossing exclusive latest start prevents dispatch");
 init(&e,&c,&f);f.guard_advance_ms=200;{uint8_t out[192];uint16_t len;assert(hms_endpoint_handle(&e,1,0,42,3,op_scaled_pair,sizeof op_scaled_pair,1000,25,out,&len));assert(out[6]==HMS_EP_START_EXPIRED&&e.operation_length==0&&e.call_high_water==0);}pass("admission guard crossing latest start does not commit claims");
 init(&e,&c,&f);admit(&e,&f);f.step_advance_ms=50;poll(&e,&f,1150,25);assert(f.dispatches==1&&e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.reason==1&&e.receipt.held_mask==5);pass("START callback crossing cutoff remains UNKNOWN");
 init(&e,&c,&f);admit(&e,&f);poll(&e,&f,1150,25);f.step_advance_ms=100;poll(&e,&f,1250,25);assert(f.effects==1&&e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.reason==2&&e.receipt.held_mask==5&&e.receipt.terminal_at==HMS_EP_TIME_ABSENT);pass("completion callback crossing run cutoff does not publish completion");
 init(&e,&c,&f);original_step=c.step;c.step=disputed_quiescence;quiescence_calls=0;admit(&e,&f);poll(&e,&f,1150,25);poll(&e,&f,1250,25);assert(e.receipt.execution==HMS_EP_COMPLETED);poll(&e,&f,1260,25);assert(e.receipt.verification==HMS_EP_DISPUTED&&e.receipt.held_mask==5);poll(&e,&f,1270,25);assert(quiescence_calls==1&&e.receipt.held_mask==5);pass("disputed terminal halts later release callbacks");
 init(&e,&c,&f);admit(&e,&f);poll(&e,&f,1150,25);e.receipt.revision=UINT32_MAX;poll(&e,&f,1250,25);assert(e.state==HMS_EP_FAULT&&e.receipt.revision==UINT32_MAX&&e.receipt.held_mask==5&&e.receipt.execution==HMS_EP_RUNNING);poll(&e,&f,1260,25);assert(f.loss_steps==1&&e.receipt.held_mask==5&&e.receipt.revision==UINT32_MAX);pass("revision exhaustion faults and retains claims without wrap");
 init(&e,&c,&f);admit(&e,&f);e.response_sequence=UINT32_MAX;memcpy(ref,op_scaled_pair,sizeof ref);ref[1]=0x21;{uint8_t out[192];uint16_t len;assert(!hms_endpoint_handle(&e,1,0,42,4,ref,sizeof ref,1000,25,out,&len));assert(e.state==HMS_EP_FAULT);}poll(&e,&f,1150,25);assert(f.dispatches==0&&e.receipt.execution==HMS_EP_REJECTED&&e.receipt.held_mask==0);pass("response exhaustion prevents queued dispatch");
 init(&e,&c,&f);admit(&e,&f);hms_endpoint_link_init(&l);memcpy(ref,op_scaled_pair,sizeof ref);ref[1]=0x21;feed(&l,&e,&f,ref,sizeof ref,4);assert(l.transmit_phase!=0);memcpy(saved,l.transmit,sizeof saved);memcpy(op,op_scaled_pair,sizeof op);op[11]=2;feed(&l,&e,&f,op,sizeof op,5);assert(e.call_high_water==1&&e.receipt.execution==HMS_EP_QUEUED);ref[1]=0x22;feed(&l,&e,&f,ref,sizeof ref,6);assert(e.receipt.execution==HMS_EP_CANCELED&&e.receipt.held_mask==0&&memcmp(saved,l.transmit,sizeof saved)==0);pass("backpressure preserves pending reply and still processes cancel");
 init(&e,&c,&f);original_step=c.step;c.step=disputed_with_release;quiescence_calls=0;admit(&e,&f);poll(&e,&f,1150,25);poll(&e,&f,1250,25);assert(e.receipt.execution==HMS_EP_COMPLETED&&e.receipt.verification==HMS_EP_DISPUTED&&e.receipt.held_mask==5);poll(&e,&f,1260,25);assert(quiescence_calls==0&&e.receipt.held_mask==5);pass("same-report DISPUTED cannot release remaining claims");
 init(&e,&c,&f);original_step=c.step;c.step=clock_loss_after_start;admit(&e,&f);poll(&e,&f,1150,25);assert(e.receipt.execution==HMS_EP_UNKNOWN&&e.receipt.reason==7&&e.receipt.held_mask==5&&e.receipt.may_have_acted==1&&e.state==HMS_EP_FAULT);pass("post-START sample detects lost clock qualification");
 init(&e,&c,&f);original_describe=c.describe;c.describe=describe_zero_alias;memcpy(op,op_scaled_pair,sizeof op);op[44]=op[45]=0;{uint8_t out[192];uint16_t len;assert(hms_endpoint_handle(&e,1,0,42,3,op,sizeof op,1000,25,out,&len));assert(out[6]!=0&&e.operation_length==0&&e.call_high_water==0&&e.receipt.held_mask==0);}pass("zero primitive ID rejected before installed metadata can alias it");
 init(&e,&c,&f);admit(&e,&f);hms_endpoint_link_init(&l);assert(hms_endpoint_link_set_receive_budget(&l,100));assert(!hms_endpoint_link_set_receive_budget(&l,0));assert(!hms_endpoint_link_set_receive_budget(&l,UINT32_MAX));hms_endpoint_link_feed(&l,&e,0x7e,1000,25);hms_endpoint_link_feed(&l,&e,'H',1000,25);hms_endpoint_link_feed(&l,&e,'M',1099,25);assert(l.receive_partial&&l.receive_started==1000);hms_endpoint_link_check_deadline(&l,1100);assert(!l.receive_partial&&!l.parser.active&&e.receipt.execution==HMS_EP_QUEUED&&e.receipt.held_mask==5&&e.call_high_water==1&&e.fence_floor[0]==5);pass("absolute receive deadline expires despite byte trickle and preserves endpoint claims");
 hms_endpoint_link_feed(&l,&e,0x7e,2000,25);hms_endpoint_link_feed(&l,&e,'H',2000,25);assert(l.receive_partial);hms_endpoint_link_check_deadline(&l,1999);assert(!l.receive_partial&&!l.parser.active&&e.receipt.held_mask==5&&e.call_high_water==1);pass("receive clock regression resets only partial parser");
 printf("%u independent original-code probes passed\n",passed);return 0;
}
