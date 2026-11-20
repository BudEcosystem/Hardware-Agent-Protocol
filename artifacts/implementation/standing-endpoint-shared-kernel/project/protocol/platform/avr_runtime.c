#include "avr_runtime.h"
#include <stddef.h>

static uint8_t constant(void *user,uint8_t which,uint8_t index) {
    hms_avr_runtime *r=user;
    return r->installed->primitive->constant_byte(r->installed->primitive->user,which,index);
}
static uint8_t describe(void *user,uint16_t primitive,const uint8_t *args,
                        uint8_t length,hms_ep_primitive *description) {
    hms_avr_runtime *r=user;
    return r->installed->primitive->describe(r->installed->primitive->user,primitive,args,length,description);
}
static uint8_t guard(void *user,uint16_t primitive,const uint8_t *args,uint8_t length) {
    hms_avr_runtime *r=user;
    return r->installed->primitive->guard(r->installed->primitive->user,primitive,args,length);
}
static void step(void *user,uint8_t phase,uint16_t primitive,const uint8_t *args,
                 uint8_t length,uint64_t tick,const hms_ep_step_limits *limits,hms_ep_report *report) {
    hms_avr_runtime *r=user;
    r->installed->primitive->step(r->installed->primitive->user,phase,primitive,args,length,tick,limits,report);
}
static uint8_t clock_snapshot(void *user,uint64_t *tick,uint16_t *flags) {
    hms_avr_runtime *r=user;
    hms_avr_clock_sample sample;
    /* Endpoint samples again after guards and driver steps. Latch ownership
     * loss here, but never reset raw parser storage while handle consumes it.
     * Startup samples precede USART ownership, hence the started==2 gate. */
    if(r->started==2u && !hms_avr_usart_current(&r->usart)) {
        r->transport_fault=1;r->flags|=HMS_EP_RECONCILE;
    }
    *flags=r->flags;
    if(hms_avr_clock_read(&r->clock,&sample)!=HMS_AVR_CLOCK_OK) {
        if(r->started==2u)r->clock_lost=1;
        *flags=(uint16_t)(*flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);return 0;
    }
    if(sample.boot_epoch!=hms_boot_reserved_epoch(&r->boot)) {
        hms_avr_clock_invalidate(&r->clock);
        if(r->started==2u)r->clock_lost=1;
        *flags=(uint16_t)(*flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);return 0;
    }
    *tick=sample.tick_ms;*flags|=HMS_EP_CLOCK_QUALIFIED;return 1;
}
static void close_faulted_receive(hms_avr_runtime *r) {
    if((r->clock_lost || r->transport_fault) && !r->receive_closed) {
        r->receive_closed=1;hms_avr_uart_discontinuity(&r->receive);
        hms_endpoint_link_reset_receive(&r->link);
    }
}
static uint8_t read_byte(void *user,uint32_t address,uint8_t *value) {
    return hms_avr_eeprom_read_byte(&((hms_avr_runtime *)user)->eeprom,address,value);
}
static uint8_t write_zero(void *user,uint32_t address) {
    return hms_avr_eeprom_program_zero_and_sync(&((hms_avr_runtime *)user)->eeprom,address);
}
static uint8_t incarnation(void *user,uint8_t index) {
    return constant(user,HMS_EP_INCARNATION,index);
}
static void before_feed(void *user,uint8_t byte) {
    hms_avr_runtime *r=user;
    hms_endpoint_link_before_feed(&r->link,byte,r->service_tick);
}
uint8_t hms_avr_runtime_start(hms_avr_runtime *r,const hms_avr_runtime_config *c) {
    uint64_t epoch,tick=0;
    uint16_t flags;
    const hms_ep_config *p;
    if(r==NULL || r->started)return 0;
    r->started=1;
    if(c==NULL || c->primitive==NULL)return 0;
    p=c->primitive;
    if(p->constant_byte==NULL || p->describe==NULL || p->guard==NULL || p->step==NULL ||
       p->resource_count==0u || p->resource_count>8u || p->max_lease_ms==0u || p->max_lease_ms>60000u ||
       c->boot_capacity==0u || c->boot_capacity>992u || c->eeprom_poll_budget==0u ||
       c->receive_budget_ms==0u || c->receive_budget_ms>UINT32_C(0x7fffffff) ||
       c->ubrr>4095u || c->double_speed>1u || c->boot_storage_assured>1u ||
       (c->clock_assurances!=0u && c->clock_assurances!=HMS_AVR_CLOCK_ALL_ASSURED) ||
       (c->clock_assurances!=0u && !c->boot_storage_assured) ||
       (c->mode_flags & (uint16_t)~78u)!=0u ||
       (c->mode_flags & 12u)==12u ||
       ((c->mode_flags&HMS_EP_STOP_COMMISSIONED)!=0u && (c->mode_flags&HMS_EP_PHYSICAL_COMMISSIONED)==0u)) return 0;
    r->installed=c;r->flags=c->mode_flags;
    hms_avr_eeprom_init(&r->eeprom,c->eeprom_poll_budget);
    r->storage=(hms_boot_storage){r,read_byte,write_zero,incarnation,0,c->boot_capacity};
    hms_boot_init(&r->boot);
    if(hms_boot_acquire(&r->boot,&r->storage)!=HMS_BOOT_RESERVED)return 0;
    epoch=hms_boot_reserved_epoch(&r->boot);
    if(c->boot_storage_assured)r->flags|=HMS_EP_BOOT_QUALIFIED;
    hms_avr_clock_init(&r->clock,epoch);
    if(hms_avr_clock_start(&r->clock)==HMS_AVR_CLOCK_FAULT)return 0;
    if(c->clock_assurances && hms_avr_clock_qualify(&r->clock,epoch,c->clock_assurances)!=HMS_AVR_CLOCK_OK)return 0;
    r->callbacks=(hms_ep_config){r,constant,describe,guard,clock_snapshot,step,p->max_lease_ms,p->resource_count};
    (void)clock_snapshot(r,&tick,&flags);
    if(!hms_endpoint_init(&r->endpoint,&r->callbacks,epoch,tick,flags))return 0;
    hms_endpoint_link_init(&r->link);hms_avr_uart_init(&r->receive);hms_avr_usart_init(&r->usart);
    if(!hms_endpoint_link_set_receive_budget(&r->link,c->receive_budget_ms))return 0;
    if(!hms_avr_usart_start(&r->usart,c->ubrr,c->double_speed))return 0;
    r->started=2;return 1;
}
void hms_avr_runtime_receive_irq(hms_avr_runtime *r) {
    if(r!=NULL && r->started==2u)hms_avr_uart_receive(&r->receive);
}
void hms_avr_runtime_overflow_irq(hms_avr_runtime *r) {
    if(r!=NULL && r->started==2u)hms_avr_clock_overflow(&r->clock);
}
void hms_avr_runtime_step(hms_avr_runtime *r) {
    hms_avr_uart_event event;
    hms_frame_result frame=HMS_FRAME_NONE;
    hms_avr_uart_result result;
    uint64_t tick;
    uint16_t flags;
    uint8_t qualified;
    if(r==NULL || r->started!=2u || r->foreground_active)return;
    r->foreground_active=1;
    tick=r->endpoint.now_tick;qualified=clock_snapshot(r,&tick,&flags);
    close_faulted_receive(r);
    if(qualified && !r->transport_fault && !r->clock_lost) {
        r->service_tick=tick;hms_endpoint_link_check_deadline(&r->link,tick);
        result=hms_avr_uart_frame_step_hook(&r->receive,&r->link.parser,&event,&frame,before_feed,r);
        if(result==HMS_AVR_UART_LOSS || result==HMS_AVR_UART_BUSY)
            hms_endpoint_link_reset_receive(&r->link);
        if(result==HMS_AVR_UART_BYTE && frame==HMS_FRAME_READY) {
            if(clock_snapshot(r,&tick,&flags) && !r->transport_fault)
                hms_endpoint_link_accept_ready(&r->link,&r->endpoint,tick,flags);
        }
    }
    /* Re-read after handling: callbacks can discover faults. Do not restore
     * stale entry flags in poll, or modify parser.raw before handle returns. */
    (void)clock_snapshot(r,&tick,&flags);close_faulted_receive(r);
    hms_endpoint_poll(&r->endpoint,tick,flags);
    close_faulted_receive(r);
    (void)hms_avr_usart_transmit(&r->usart,&r->link);
    r->foreground_active=0;
}
