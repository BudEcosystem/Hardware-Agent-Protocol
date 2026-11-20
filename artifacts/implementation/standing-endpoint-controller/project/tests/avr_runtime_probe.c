#include "../protocol/platform/avr_runtime.h"
#include "endpoint_fixture.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks,cases;
#define CHECK(x) do { ++checks;if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1);} } while(0)
#define CASE(x) do{x();++cases;}while(0)
static hms_avr_runtime r;
static hms_endpoint_fixture f;
static hms_ep_config primitive;
static hms_avr_runtime_config installation;
static uint8_t status_register,port[7],timer[10],eeprom[1024],received,latched_high;
static uint16_t eeprom_address;
static uint64_t raw_ticks;
static uint8_t transmitted[8192];
static unsigned transmitted_count,programs,write_order,udr_order,clear_order;
static uint8_t loss_during_feed,loss_after_ready,clock_after_ready,ready_seen,complete_between_writes;
static uint8_t drift_during_guard;
static uint8_t check_admission_parser;
static unsigned admission_parser_observations;
static uint8_t (*installed_guard)(void *,uint16_t,const uint8_t *,uint8_t);
static uint8_t model_guard(void *user,uint16_t id,const uint8_t *args,uint8_t length){
    uint8_t result=installed_guard(user,id,args,length);
    if(drift_during_guard){drift_during_guard=0;port[2]^=1u;}
    return result;
}

static uint8_t save_cli(void){uint8_t saved=status_register;status_register&=0x7fu;return saved;}
static void restore(uint8_t saved){status_register=saved;}
uint8_t hms_avr_probe_save_cli(void){return save_cli();}
void hms_avr_probe_restore(uint8_t saved){restore(saved);}
uint8_t hms_avr_probe_control(void){return 0;}
uint8_t hms_avr_probe_spm(void){return 0;}
void hms_avr_probe_address(uint16_t address){CHECK(address<1024u);eeprom_address=address;}
uint8_t hms_avr_probe_read(void){return eeprom[eeprom_address];}
void hms_avr_probe_launch_zero(void){CHECK((status_register&0x80u)==0u);eeprom[eeprom_address]=0;++programs;}
uint8_t hms_avr_clock_probe_save_cli(void){return save_cli();}
void hms_avr_clock_probe_restore(uint8_t saved){restore(saved);}
uint8_t hms_avr_clock_probe_read(uint8_t reg){
    CHECK(reg<10u);
    if(check_admission_parser && r.transport_fault && r.endpoint.callback_active){
        CHECK(r.link.parser.active==1u && r.link.parser.raw[0]=='H' && r.link.parser.raw[1]=='M');
        CHECK(r.link.parser.raw[20]==1u && r.link.parser.raw[21]==32u);
        ++admission_parser_observations;
    }
    if(reg==5u){latched_high=(uint8_t)(raw_ticks>>8);return(uint8_t)raw_ticks;}
    if(reg==6u)return latched_high;
    return timer[reg];
}
void hms_avr_clock_probe_write(uint8_t reg,uint8_t value){
    CHECK(reg<10u);
    if(reg==4u)timer[reg]&=(uint8_t)~value;
    else if(reg==6u)latched_high=value;
    else if(reg==5u)raw_ticks=(uint16_t)(((uint16_t)latched_high<<8)|value);
    else timer[reg]=value;
}
uint8_t hms_avr_uart_probe_save_cli(void){return save_cli();}
void hms_avr_uart_probe_restore(uint8_t saved){
    restore(saved);
    if(loss_after_ready && ready_seen && !r.receive.foreground_active){
        loss_after_ready=0;ready_seen=0;hms_avr_uart_discontinuity(&r.receive);
    }
}
uint8_t hms_avr_uart_probe_status(void){return port[0];}
uint8_t hms_avr_uart_probe_data(void){port[0]&=0x63u;return received;}
hms_frame_result hms_avr_uart_probe_feed(hms_frame_parser *parser,uint8_t byte){
    hms_frame_result result=hms_frame_feed(parser,byte);
    if(result==HMS_FRAME_READY){
        ready_seen=1;
        if(loss_during_feed){loss_during_feed=0;hms_avr_uart_discontinuity(&r.receive);}
        if(clock_after_ready){clock_after_ready=0;hms_avr_clock_invalidate(&r.clock);}
    }
    return result;
}
uint8_t hms_avr_usart_probe_save_cli(void){return save_cli();}
void hms_avr_usart_probe_restore(uint8_t saved){restore(saved);}
uint8_t hms_avr_usart_probe_read(uint8_t reg){CHECK(reg<7u);return port[reg];}
void hms_avr_usart_probe_write(uint8_t reg,uint8_t value){
    CHECK(reg<7u);++write_order;
    if(reg==5u){
        CHECK((status_register&0x80u)==0u);CHECK((port[0]&0x20u)!=0u);
        CHECK(transmitted_count<sizeof(transmitted));transmitted[transmitted_count++]=value;
        port[0]&=(uint8_t)~0x20u;udr_order=write_order;
        if(complete_between_writes)port[0]|=0x40u;
    }else if(reg==0u){
        CHECK((value&0xbcu)==0u);port[0]=(uint8_t)((port[0]&0xfcu)|(value&3u));
        if(value&0x40u){CHECK((status_register&0x80u)==0u);port[0]&=(uint8_t)~0x40u;clear_order=write_order;}
    }else port[reg]=value;
}

static void p16(uint8_t *p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void p32(uint8_t *p,uint32_t v){unsigned i;for(i=0;i<4;++i){p[3-i]=(uint8_t)v;v>>=8;}}
static void p64(uint8_t *p,uint64_t v){unsigned i;for(i=0;i<8;++i){p[7-i]=(uint8_t)v;v>>=8;}}
static uint16_t crc(const uint8_t *p,uint16_t n){
    uint16_t value=0xffffu,i;unsigned bit;
    for(i=0;i<n;++i){value^=p[i];for(bit=0;bit<8;++bit)value=(uint16_t)((value>>1)^((value&1u)?0x8408u:0u));}
    return(uint16_t)(value^0xffffu);
}
static uint16_t encode(uint8_t *out,const uint8_t *payload,uint16_t length,uint64_t boot,uint32_t sequence){
    uint8_t raw[214];uint16_t i,n=0,value;
    CHECK(length<=192u);memset(raw,0,sizeof(raw));raw[0]='H';raw[1]='M';raw[2]=1;raw[3]=1;
    p64(raw+6,boot);p32(raw+14,sequence);p16(raw+18,length);memcpy(raw+20,payload,length);
    value=crc(raw,(uint16_t)(20u+length));raw[20u+length]=(uint8_t)value;raw[21u+length]=(uint8_t)(value>>8);
    out[n++]=0x7e;
    for(i=0;i<22u+length;++i){if(raw[i]==0x7d||raw[i]==0x7e){out[n++]=0x7d;out[n++]=(uint8_t)(raw[i]^0x20);}else out[n++]=raw[i];}
    out[n++]=0x7e;CHECK(n<=430u);return n;
}
static void model_reset(uint8_t keep_bank){
    memset(&r,0,sizeof(r));memset(port,0,sizeof(port));memset(timer,0,sizeof(timer));
    status_register=0;port[0]=0x20;raw_ticks=0;transmitted_count=0;write_order=udr_order=clear_order=0;
    loss_during_feed=loss_after_ready=clock_after_ready=ready_seen=complete_between_writes=0;
    drift_during_guard=0;
    check_admission_parser=0;admission_parser_observations=0;
    if(!keep_bank){memset(eeprom,0xff,sizeof(eeprom));programs=0;}
    hms_endpoint_fixture_init(&f,&primitive);
    installed_guard=primitive.guard;primitive.guard=model_guard;
    installation=(hms_avr_runtime_config){&primitive,1000,16,8,25,HMS_EP_SIMULATOR_ONLY,0,1,HMS_AVR_CLOCK_ALL_ASSURED};
}
static void provision(void){
    unsigned i;memcpy(eeprom,"HMSBOOT1",8);
    for(i=0;i<16;++i)eeprom[8+i]=primitive.constant_byte(primitive.user,HMS_EP_INCARNATION,(uint8_t)i);
    eeprom[24]=0;eeprom[25]=8;memset(eeprom+26,0,6);
}
static void start(void){model_reset(0);provision();CHECK(hms_avr_runtime_start(&r,&installation));CHECK(programs==1u);status_register=0x80;}
static void advance(uint64_t ms){
    uint64_t target=ms*250u;
    CHECK(target>=raw_ticks);
    while((raw_ticks>>16)!=(target>>16)){
        uint8_t saved=status_register;raw_ticks=((raw_ticks>>16)+1u)<<16;timer[4]=0;
        status_register&=0x7f;hms_avr_runtime_overflow_irq(&r);status_register=saved;
    }
    raw_ticks=target;
}
static void receive(uint8_t byte,uint8_t errors){
    uint8_t saved=status_register;received=byte;port[0]=(uint8_t)((port[0]&0x63u)|0x80u|errors);
    status_register&=0x7fu;hms_avr_runtime_receive_irq(&r);status_register=saved;
}
static void feed(const uint8_t *wire,uint16_t n){uint16_t i;for(i=0;i<n;++i){receive(wire[i],0);port[0]|=0x20;hms_avr_runtime_step(&r);}}
static void drain(void){unsigned i;for(i=0;i<431u && r.link.transmit_phase;++i){port[0]|=0x20;hms_avr_runtime_step(&r);}CHECK(!r.link.transmit_phase);}
static void hello(uint8_t *wire,uint16_t *n){const uint8_t payload[]={1,1};*n=encode(wire,payload,2,0,0);}
static uint8_t direct(uint8_t *p,uint16_t n,uint32_t seq){
    uint8_t out[192];uint16_t length=0;
    CHECK(hms_endpoint_handle(&r.endpoint,1,0,r.endpoint.boot_epoch,seq,p,n,1000,
        HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_SIMULATOR_ONLY,out,&length));
    CHECK(length>=7u);return out[6];
}
static uint8_t wire_request(uint8_t *p,uint16_t n,uint32_t seq){
    uint8_t wire[430];uint16_t length;hms_frame_parser reply;unsigned i,ready=0,before=transmitted_count;
    length=encode(wire,p,n,r.endpoint.boot_epoch,seq);feed(wire,length);drain();
    hms_frame_reset(&reply);
    for(i=before;i<transmitted_count;++i)if(hms_frame_feed(&reply,transmitted[i])==HMS_FRAME_READY)++ready;
    CHECK(ready==1 && reply.raw[3]==2 && reply.raw[20]==1);return reply.raw[26];
}
static uint8_t admit_using(uint8_t wire){
    uint8_t p[104];unsigned i;advance(1000);
    memset(p,0,sizeof(p));p[0]=1;p[1]=16;p32(p+2,1);p16(p+6,7);
    for(i=0;i<32;++i){p[8+i]=primitive.constant_byte(primitive.user,HMS_EP_MANIFEST,(uint8_t)i);p[40+i]=(uint8_t)(0x40u+i);}
    CHECK((wire?wire_request(p,72,1):direct(p,72,1))==0);
    memset(p,0,sizeof(p));p[0]=1;p[1]=17;p32(p+2,2);p16(p+6,7);for(i=0;i<32;++i)p[8+i]=(uint8_t)(0x40u+i);
    p64(p+40,2000);CHECK((wire?wire_request(p,48,2):direct(p,48,2))==0);
    memset(p,0,sizeof(p));p[0]=1;p[1]=32;p32(p+2,2);p16(p+6,7);p32(p+8,1);
    for(i=0;i<32;++i)p[12+i]=(uint8_t)(0x60u+i);
    p16(p+44,0x1234);p[46]=5;p[47]=8;p64(p+52,1100);p64(p+60,1200);p64(p+68,1500);p32(p+76,200);p64(p+80,1600);
    p32(p+88,5);p32(p+92,9);p32(p+96,1000);p32(p+100,0xffffffe7u);
    if(wire==2u){
        uint8_t bytes[430];uint16_t count;
        drift_during_guard=1;check_admission_parser=1;
        count=encode(bytes,p,104,r.endpoint.boot_epoch,3);feed(bytes,count);
        CHECK(r.link.transmit_phase!=0);return r.link.transmit[26];
    }
    return wire?wire_request(p,104,3):direct(p,104,3);
}
static void admit(void){CHECK(admit_using(0)==0);}

void hms_reference_link_init(hms_endpoint_link *);
void hms_reference_link_feed(hms_endpoint_link *,hms_endpoint *,uint8_t,uint64_t,uint16_t);
uint8_t hms_reference_link_next(hms_endpoint_link *,uint8_t *);
static void factorization_oracle(void){
    hms_endpoint a,b;hms_endpoint_link x,y;hms_endpoint_fixture fixture;hms_ep_config config;
    uint8_t wire[430],u,v;uint16_t n;unsigned i,j;uint32_t random=7;
    hms_endpoint_fixture_init(&fixture,&config);
    CHECK(hms_endpoint_init(&a,&config,42,1000,25));CHECK(hms_endpoint_init(&b,&config,42,1000,25));
    hms_endpoint_link_init(&x);hms_reference_link_init(&y);hello(wire,&n);
    for(i=0;i<20000u;++i){
        random=random*1664525u+1013904223u;u=(uint8_t)(random>>24);
        if(i%97u<n)u=wire[i%97u];
        hms_endpoint_link_feed(&x,&a,u,1000u+i/50u,25);hms_reference_link_feed(&y,&b,u,1000u+i/50u,25);
        CHECK(!memcmp(&x,&y,sizeof(x)));CHECK(!memcmp(&a,&b,sizeof(a)));
        for(j=0;j<(i%7u==0u?2u:0u);++j){
            uint8_t have=hms_endpoint_link_next(&x,&u),reference=hms_reference_link_next(&y,&v);
            CHECK(have==reference);if(have)CHECK(u==v);
        }
    }
}
static void complete_register_path(void){
    uint8_t wire[430];uint16_t n;hms_frame_parser reply;unsigned i,ready=0;
    start();hello(wire,&n);feed(wire,n);CHECK(r.endpoint.response_sequence==1);drain();
    hms_frame_reset(&reply);for(i=0;i<transmitted_count;++i)if(hms_frame_feed(&reply,transmitted[i])==HMS_FRAME_READY)++ready;
    CHECK(ready==1);CHECK(reply.raw[3]==2 && reply.raw[20]==1 && reply.raw[21]==129 && reply.raw[26]==0);
    CHECK(!hms_avr_usart_drained(&r.usart,&r.link));port[0]|=0x40;CHECK(hms_avr_usart_drained(&r.usart,&r.link));
    CHECK(status_register==0x80);CHECK(udr_order<clear_order && clear_order==udr_order+1u);
}
static void loss_at_ready(void){
    uint8_t wire[430];uint16_t n;
    start();hello(wire,&n);loss_during_feed=1;feed(wire,n);CHECK(r.endpoint.response_sequence==0);CHECK(!r.link.receive_partial);
    feed(wire,n);CHECK(r.endpoint.response_sequence==1);
    start();hello(wire,&n);loss_after_ready=1;feed(wire,n);CHECK(r.endpoint.response_sequence==1);CHECK(r.receive.loss!=0);
    hms_avr_runtime_step(&r);CHECK(!r.receive.loss);CHECK(r.endpoint.response_sequence==1);
    start();hello(wire,&n);clock_after_ready=1;feed(wire,n);CHECK(r.endpoint.response_sequence==0);CHECK(r.clock_lost);
}
static void drop_before_feed(void *user,uint8_t byte){
    hms_avr_runtime *runtime=user;
    hms_endpoint_link_before_feed(&runtime->link,byte,runtime->service_tick);
    hms_avr_uart_discontinuity(&runtime->receive);
}
static void loss_in_before_feed(void){
    uint8_t wire[430];uint16_t n;hms_avr_uart_event event;hms_frame_result frame=HMS_FRAME_NONE;
    start();hello(wire,&n);feed(wire,(uint16_t)(n-1u));receive(wire[n-1u],0);
    CHECK(hms_avr_uart_frame_step_hook(&r.receive,&r.link.parser,&event,&frame,drop_before_feed,&r)==HMS_AVR_UART_LOSS);
    CHECK(frame==HMS_FRAME_NONE && r.endpoint.response_sequence==0 && !r.link.parser.active);
    hms_endpoint_link_reset_receive(&r.link);feed(wire,n);CHECK(r.endpoint.response_sequence==1);
}
static void finite_operation_over_wire(void){
    uint8_t p[44];unsigned i;
    start();CHECK(admit_using(1)==0);CHECK(r.endpoint.receipt.execution==HMS_EP_QUEUED && !f.dispatches);
    advance(1150);hms_avr_runtime_step(&r);CHECK(f.dispatches==1 && r.endpoint.receipt.held_mask==5);
    advance(1250);hms_avr_runtime_step(&r);CHECK(f.effects==1 && r.endpoint.receipt.execution==HMS_EP_COMPLETED);
    CHECK(r.endpoint.receipt.held_mask==5);hms_avr_runtime_step(&r);CHECK(!r.endpoint.receipt.held_mask);
    memset(p,0,sizeof(p));p[0]=1;p[1]=33;p32(p+2,2);p16(p+6,7);p32(p+8,1);
    CHECK(wire_request(p,12,4)==HMS_EP_BAD_LENGTH);CHECK(f.dispatches==1 && f.effects==1);
    for(i=0;i<32u;++i)p[12+i]=(uint8_t)(0x60u+i);
    CHECK(wire_request(p,44,5)==0);CHECK(f.dispatches==1 && f.effects==1);
}
static void wire_admission_guard_drift(void){
    start();CHECK(admit_using(2)==HMS_EP_RECONCILIATION_REQUIRED);
    CHECK(r.transport_fault && r.receive_closed && (r.endpoint.flags&HMS_EP_RECONCILE));
    CHECK(!r.endpoint.operation_length && !r.endpoint.receipt.held_mask && !r.endpoint.call_high_water);
    CHECK(!r.endpoint.fence_floor[0] && !r.endpoint.fence_floor[2] && !f.dispatches);
    CHECK(!r.link.parser.active && !r.link.receive_partial);
    CHECK(admission_parser_observations>0);
    /* Model observes active parser/payload during the post-guard snapshot,
     * then stable cleanup after handle. Faulty USART cannot transmit reply. */
    CHECK(r.link.transmit[21]==160u && r.link.transmit[26]==HMS_EP_RECONCILIATION_REQUIRED);
}
static void idle_deadline_and_errors(void){
    uint8_t wire[430];uint16_t n;unsigned i;
    start();CHECK(hms_endpoint_link_set_receive_budget(&r.link,10));hello(wire,&n);feed(wire,4);
    CHECK(r.link.receive_partial);advance(10);hms_avr_runtime_step(&r);CHECK(!r.link.receive_partial && !r.link.parser.active);
    feed(wire+4,(uint16_t)(n-4u));CHECK(!r.endpoint.response_sequence);
    feed(wire,n);CHECK(r.endpoint.response_sequence==1);
    for(i=0;i<3;++i){start();hello(wire,&n);feed(wire,4);receive(0x55,(uint8_t)(4u<<i));hms_avr_runtime_step(&r);CHECK(!r.link.parser.active && !r.link.receive_partial);CHECK(!r.endpoint.response_sequence);}
    start();for(i=0;i<17u;++i)receive((uint8_t)i,0);CHECK(r.receive.loss&HMS_AVR_UART_RING_FULL);hms_avr_runtime_step(&r);CHECK(!r.receive.loss && !r.link.parser.active);
}
static void stalled_tx_services_operation(void){
    uint16_t before;
    start();admit();r.link.transmit_phase=2;r.link.transmit_length=2;r.link.transmit[0]=0x31;r.link.transmit[1]=0x32;
    port[0]&=(uint8_t)~0x20u;before=r.link.transmit_index;advance(1150);hms_avr_runtime_step(&r);
    CHECK(f.dispatches==1);CHECK(r.link.transmit_index==before);f.mode=HMS_FIXTURE_NEVER_COMPLETE;
    advance(1350);hms_avr_runtime_step(&r);CHECK(f.loss_steps==1);CHECK(r.endpoint.receipt.reason==2);CHECK(r.endpoint.receipt.held_mask==5);
    CHECK(r.link.transmit_index==before);hms_avr_runtime_step(&r);CHECK(r.endpoint.receipt.held_mask==0);
}
static void startup_and_boot_boundaries(void){
    unsigned count;
    model_reset(0);provision();installation.receive_budget_ms=0;CHECK(!hms_avr_runtime_start(&r,&installation));CHECK(programs==0);
    model_reset(0);provision();installation.receive_budget_ms=UINT32_C(0x80000000);CHECK(!hms_avr_runtime_start(&r,&installation));CHECK(programs==0);
    model_reset(0);provision();installation.receive_budget_ms=37;CHECK(hms_avr_runtime_start(&r,&installation));CHECK(r.link.receive_budget_ms==37);
    model_reset(0);CHECK(!hms_avr_runtime_start(&r,&installation));count=programs;CHECK(!hms_avr_runtime_start(&r,&installation));CHECK(programs==count);
    model_reset(0);provision();installation.boot_storage_assured=0;installation.clock_assurances=0;
    CHECK(hms_avr_runtime_start(&r,&installation));CHECK(!(r.endpoint.flags&HMS_EP_BOOT_QUALIFIED));CHECK(r.endpoint.flags&HMS_EP_INHIBITED);
    start();CHECK(r.endpoint.boot_epoch==1);count=programs;CHECK(!hms_avr_runtime_start(&r,&installation));CHECK(programs==count);
    model_reset(1);CHECK(hms_avr_runtime_start(&r,&installation));CHECK(r.endpoint.boot_epoch==2 && programs==count+1u);
}
static void configuration_and_clock_fault(void){
    start();port[1]|=2;CHECK(hms_avr_usart_current(&r.usart));port[1]&=(uint8_t)~2u;
    port[2]^=1;hms_avr_runtime_step(&r);CHECK(r.transport_fault && (r.flags&HMS_EP_RECONCILE));CHECK(r.usart.fault);
    start();admit();advance(1150);hms_avr_runtime_step(&r);hms_avr_clock_invalidate(&r.clock);hms_avr_runtime_step(&r);
    CHECK(r.clock_lost && r.endpoint.state==HMS_EP_FAULT);CHECK(f.loss_steps==1);CHECK(r.endpoint.receipt.reason==7);
    CHECK(r.endpoint.receipt.held_mask==5);CHECK(r.receive.loss);
    start();admit();advance(1150);drift_during_guard=1;hms_avr_runtime_step(&r);
    CHECK(r.transport_fault && r.receive_closed);CHECK(r.endpoint.flags&HMS_EP_RECONCILE);
    CHECK(!f.dispatches && r.endpoint.receipt.execution==HMS_EP_REJECTED);
    CHECK(!r.endpoint.receipt.may_have_acted && !r.endpoint.receipt.held_mask);
    CHECK(!r.link.parser.active && !r.link.receive_partial);
}
static void tx_interrupt_state_and_completion_race(void){
    unsigned s;hms_avr_usart p;hms_endpoint_link link;
    for(s=0;s<256u;++s){
        model_reset(0);status_register=(uint8_t)s;hms_avr_usart_init(&p);CHECK(hms_avr_usart_start(&p,25,0));CHECK(status_register==(uint8_t)s);
        hms_endpoint_link_init(&link);link.transmit_phase=2;link.transmit_length=1;link.transmit[0]=0x7d;
        port[0]&=(uint8_t)~0x20u;CHECK(hms_avr_usart_transmit(&p,&link)==HMS_AVR_USART_WAIT);CHECK(link.transmit_index==0 && !transmitted_count);
        port[0]|=0x60;complete_between_writes=1;CHECK(hms_avr_usart_transmit(&p,&link)==HMS_AVR_USART_SENT);CHECK(status_register==(uint8_t)s);
        CHECK(!(port[0]&0x40u));CHECK(transmitted_count==1 && transmitted[0]==0x7d);CHECK(link.escape_pending==0x7d);
        CHECK(!hms_avr_usart_drained(&p,&link));CHECK(udr_order+1u==clear_order);
    }
}
int main(void){
    CASE(factorization_oracle);CASE(complete_register_path);CASE(loss_at_ready);CASE(idle_deadline_and_errors);
    CASE(stalled_tx_services_operation);CASE(startup_and_boot_boundaries);CASE(configuration_and_clock_fault);CASE(tx_interrupt_state_and_completion_race);
    CASE(loss_in_before_feed);CASE(finite_operation_over_wire);
    CASE(wire_admission_guard_drift);
    printf("{\"status\":\"passed\",\"cases\":%u,\"assertions\":%u,\"wireOracleSteps\":20000,\"interruptSnapshots\":256,\"targetExecuted\":false}\n",cases,checks);return 0;
}
