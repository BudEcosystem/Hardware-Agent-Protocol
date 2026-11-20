/* Combined compile/link image only. No target execution or physical drivers.
 * No qualification is invented: zero assurance keeps ordinary effects inhibited.
 * The installed fixture remains synthetic. A physical application requires a
 * separate commissioned callback/identity/stop integration and fresh analysis. */
#include "../protocol/platform/avr_runtime.h"
#include "endpoint_fixture.h"
#include <avr/io.h>
#include <avr/interrupt.h>

hms_avr_runtime hms_target_runtime;
hms_endpoint_fixture hms_target_fixture;
hms_ep_config hms_target_primitive;
hms_avr_runtime_config hms_target_installation;
volatile uint8_t hms_target_initialized;
/* Preserve the earlier full 256-byte primitive allowance and an explicit
 * 64-byte protection-service allowance. These retained arrays are reservations,
 * not implemented independent protection or evidence of qualified capacity. */
volatile uint8_t hms_target_primitive_reserve[256u-sizeof(hms_endpoint_fixture)];
volatile uint8_t hms_target_protection_reserve[64];
_Static_assert(sizeof(hms_endpoint_fixture)<256u,"Primitive allowance exceeded");
_Static_assert(sizeof(hms_frame_parser)==219u,"Expected ATmega328P parser ABI");
ISR(USART_RX_vect){hms_avr_runtime_receive_irq(&hms_target_runtime);}
ISR(TIMER1_OVF_vect){hms_avr_runtime_overflow_irq(&hms_target_runtime);}
int main(void){
    cli();hms_endpoint_fixture_init(&hms_target_fixture,&hms_target_primitive);
    hms_target_installation=(hms_avr_runtime_config){&hms_target_primitive,1000u,65535u,992u,25u,HMS_EP_SIMULATOR_ONLY,0,0,0};
    hms_target_primitive_reserve[0]=0;hms_target_protection_reserve[0]=0;
    hms_target_initialized=hms_avr_runtime_start(&hms_target_runtime,&hms_target_installation);
    if(hms_target_initialized)sei();
    for(;;)if(hms_target_initialized)hms_avr_runtime_step(&hms_target_runtime);
}
