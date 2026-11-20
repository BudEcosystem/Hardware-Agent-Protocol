/* Compile/link-only actual AVR adapter composition, never a physical driver. */
#include "../protocol/platform/avr_runtime.h"
#include "standing_fixture.h"
#include <avr/io.h>
#include <avr/interrupt.h>
hms_avr_runtime hms_target_runtime;
hms_standing hms_target_standing;
hms_st_arena hms_target_arena;
hms_ep_config hms_target_primitive;
hms_st_config hms_target_controller;
hms_avr_runtime_config hms_target_installation;
volatile uint8_t hms_target_initialized;
/* Charge the entire proposed32B glue ceiling, including endpoint's new
 * attachment pointer, controller's three pointers and installed configuration. */
#define GLUE_USED (sizeof(hms_standing)-128u+sizeof(hms_st_config)+sizeof(void *))
_Static_assert(sizeof(void *)==2u,"Expected ATmega328P data-pointer ABI");
_Static_assert(GLUE_USED<32u,"Standing glue must leave a positive explicit reserve within32B");
volatile uint8_t hms_target_glue_reserve[32u-GLUE_USED];
volatile uint8_t hms_target_protection_reserve[64];
_Static_assert(sizeof(hms_st_arena)==256u,"Full primitive allowance must remain256B");
_Static_assert(sizeof(hms_frame_parser)==219u,"Expected ATmega328P parser ABI");
ISR(USART_RX_vect){hms_avr_runtime_receive_irq(&hms_target_runtime);}
ISR(TIMER1_OVF_vect){hms_avr_runtime_overflow_irq(&hms_target_runtime);}
int main(void){
    cli();hms_st_fixture_init(&hms_target_arena,&hms_target_primitive,&hms_target_controller);
    hms_target_installation=(hms_avr_runtime_config){&hms_target_primitive,1000u,65535u,992u,25u,HMS_EP_SIMULATOR_ONLY,0,0,0};
    hms_target_protection_reserve[0]=0;hms_target_glue_reserve[0]=0;
    hms_target_initialized=hms_avr_runtime_start(&hms_target_runtime,&hms_target_installation);
    if(hms_target_initialized)hms_target_initialized=hms_standing_attach(&hms_target_standing,
        &hms_target_runtime.endpoint,&hms_target_controller,&hms_target_arena);
    if(hms_target_initialized)sei();
    for(;;)if(hms_target_initialized)hms_avr_runtime_step(&hms_target_runtime);
}
