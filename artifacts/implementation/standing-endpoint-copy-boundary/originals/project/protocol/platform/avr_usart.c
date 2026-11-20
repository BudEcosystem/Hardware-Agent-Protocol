#include "avr_usart.h"
#include <stddef.h>

#if defined(HMS_AVR_USART_TEST)
extern uint8_t hms_avr_usart_probe_save_cli(void);
extern void hms_avr_usart_probe_restore(uint8_t);
extern uint8_t hms_avr_usart_probe_read(uint8_t);
extern void hms_avr_usart_probe_write(uint8_t,uint8_t);
#define save_cli hms_avr_usart_probe_save_cli
#define restore hms_avr_usart_probe_restore
#define READ(reg) hms_avr_usart_probe_read(reg)
#define WRITE(reg,value) hms_avr_usart_probe_write((reg),(value))
enum { R_A, R_B, R_C, R_LOW, R_HIGH, R_DATA, R_POWER };
#else
#if !defined(__AVR_ATmega328P__) || !defined(F_CPU) || F_CPU != 16000000UL
#error "This USART owner profile requires ATmega328P and declared 16 MHz"
#endif
#include <avr/io.h>
#include <avr/interrupt.h>
_Static_assert(_SFR_MEM_ADDR(UCSR0A)==0xc0 && _SFR_MEM_ADDR(UDR0)==0xc6,
               "Reviewed USART0 addresses");
_Static_assert(TXC0==6 && UDRE0==5 && U2X0==1 && PRUSART0==1,
               "Reviewed USART0 status/power bits");
static uint8_t save_cli(void) { uint8_t saved=SREG;cli();return saved; }
static void restore(uint8_t saved) { __asm__ __volatile__("" ::: "memory");SREG=saved; }
#define READ(reg) (reg)
#define WRITE(reg,value) ((reg)=(value))
#define R_A UCSR0A
#define R_B UCSR0B
#define R_C UCSR0C
#define R_LOW UBRR0L
#define R_HIGH UBRR0H
#define R_DATA UDR0
#define R_POWER PRR
#endif

static uint8_t current(hms_avr_usart *p) {
    if (!p->started || p->fault || (READ(R_POWER)&2u)!=0u ||
        (READ(R_A)&3u)!=p->u2x || (READ(R_B)&0xfdu)!=0x98u || READ(R_C)!=6u ||
        READ(R_LOW)!=(uint8_t)p->ubrr || READ(R_HIGH)!=(uint8_t)(p->ubrr>>8)) {
        p->fault=1;return 0;
    }
    return 1;
}
void hms_avr_usart_init(hms_avr_usart *p) {
    if(p==NULL)return;
    p->ubrr=0;p->u2x=0;p->started=0;p->fault=0;p->wrote=0;p->active=0;
}
uint8_t hms_avr_usart_start(hms_avr_usart *p,uint16_t ubrr,uint8_t double_speed) {
    uint8_t saved,result=0;
    if(p==NULL)return 0;
    saved=save_cli();
    if(p->started || p->active || p->fault || ubrr>4095u || double_speed>1u ||
       (READ(R_B)&0xfdu)!=0u || (READ(R_A)&0x80u)!=0u || (READ(R_POWER)&2u)!=0u) p->fault=1;
    p->started=1;
    if(!p->fault) {
        p->ubrr=ubrr;p->u2x=double_speed?2u:0u;
        WRITE(R_HIGH,(uint8_t)(ubrr>>8));WRITE(R_LOW,(uint8_t)ubrr);
        WRITE(R_C,6u);WRITE(R_A,p->u2x);WRITE(R_B,0x98u);
        result=current(p);
    }
    restore(saved);return result;
}
uint8_t hms_avr_usart_current(hms_avr_usart *p) {
    uint8_t saved,result;
    if(p==NULL)return 0;
    saved=save_cli();result=current(p);restore(saved);return result;
}
hms_avr_usart_result hms_avr_usart_transmit(hms_avr_usart *p,hms_endpoint_link *l) {
    uint8_t saved,byte;
    hms_avr_usart_result result;
    if(p==NULL || l==NULL)return HMS_AVR_USART_FAULT;
    saved=save_cli();
    if(p->active) { restore(saved);return HMS_AVR_USART_BUSY; }
    p->active=1;
    if(!current(p))result=HMS_AVR_USART_FAULT;
    else if((READ(R_A)&0x20u)==0u)result=HMS_AVR_USART_WAIT;
    else if(!hms_endpoint_link_next(l,&byte))result=HMS_AVR_USART_IDLE;
    else {
        WRITE(R_DATA,byte);
        WRITE(R_A,(uint8_t)(p->u2x|0x40u));
        p->wrote=1;result=HMS_AVR_USART_SENT;
    }
    p->active=0;restore(saved);return result;
}
uint8_t hms_avr_usart_drained(hms_avr_usart *p,const hms_endpoint_link *l) {
    uint8_t saved,result=0;
    if(p==NULL || l==NULL)return 0;
    saved=save_cli();
    if(!p->active && current(p) && l->transmit_phase==0u)
        result=(uint8_t)(!p->wrote || (READ(R_A)&0x40u)!=0u);
    restore(saved);return result;
}
