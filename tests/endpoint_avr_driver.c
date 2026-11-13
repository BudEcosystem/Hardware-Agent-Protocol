/* Original build-only AVR harness. Never flashed or executed on a target.
 * Input/output and time are synthetic volatile mailboxes, not UART registers
 * or an atomic qualified clock. All endpoint/framing and installed fixture
 * callbacks remain reachable; no hardware capability is supplied by this file.
 */
#include "../protocol/endpoint/link.h"
#include "endpoint_fixture.h"

hms_endpoint hms_avr_endpoint;
hms_endpoint_link hms_avr_link;
hms_endpoint_fixture hms_avr_fixture;
hms_ep_config hms_avr_config;

/* These retained arrays reserve storage only. They implement no UART queue,
 * interrupt service, timer extension, NVM journal, independent stop or driver.
 * The synthetic fixture consumes part of the 256-byte primitive state budget.
 */
volatile uint8_t hms_avr_uart_rx_reserve[70];
volatile uint8_t hms_avr_uart_tx_reserve[67];
volatile uint8_t hms_avr_platform_reserve[64];
volatile uint8_t hms_avr_primitive_reserve[256u - sizeof(hms_endpoint_fixture)];

volatile uint8_t hms_avr_input;
volatile uint8_t hms_avr_input_ready;
volatile uint8_t hms_avr_output;
volatile uint8_t hms_avr_output_ready;
volatile uint8_t hms_avr_reset_receive;
volatile uint8_t hms_avr_set_receive_budget;
volatile uint32_t hms_avr_receive_budget_ms = 1000;
volatile uint64_t hms_avr_tick = 1000;
volatile uint16_t hms_avr_platform_flags = HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED;
volatile uint8_t hms_avr_fixture_mode;
volatile uint8_t hms_avr_guard_denied;
volatile uint32_t hms_avr_guard_advance_ms;
volatile uint32_t hms_avr_step_advance_ms;
volatile uint8_t hms_avr_init_result;
volatile uint8_t hms_avr_budget_result;
uint8_t hms_avr_next_byte;

_Static_assert(sizeof(unsigned int) == 2u, "Expected AVR 16-bit int");
_Static_assert(sizeof(unsigned long) == 4u, "Expected AVR 32-bit long");
_Static_assert(sizeof(void *) == 2u, "Expected AVR 16-bit data pointer");
_Static_assert(sizeof(hms_frame_parser) == 219u, "Unexpected AVR parser layout");
_Static_assert(sizeof(hms_endpoint_fixture) < 256u, "Fixture exceeds primitive-state reservation");

int main(void) {
    hms_endpoint_fixture_init(&hms_avr_fixture, &hms_avr_config);
    /* Epoch 7 and qualification flags are test inputs only. No NVM commit,
     * clock qualification, device identity or commissioning happened.
     */
    hms_avr_init_result = hms_endpoint_init(&hms_avr_endpoint, &hms_avr_config,
                                           UINT64_C(7), hms_avr_fixture.clock_tick,
                                           hms_avr_fixture.platform_flags);
    hms_endpoint_link_init(&hms_avr_link);
    /* Volatile references keep each entire reservation in the final image. */
    hms_avr_uart_rx_reserve[0] = 0;
    hms_avr_uart_tx_reserve[0] = 0;
    hms_avr_platform_reserve[0] = 0;
    hms_avr_primitive_reserve[0] = 0;
    for (;;) {
        hms_avr_fixture.clock_tick = hms_avr_tick;
        hms_avr_fixture.platform_flags = (uint16_t)((hms_avr_platform_flags &
            (HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_RECONCILE)) |
            HMS_EP_SIMULATOR_ONLY);
        hms_avr_fixture.mode = hms_avr_fixture_mode;
        hms_avr_fixture.guard_denied = hms_avr_guard_denied;
        hms_avr_fixture.guard_advance_ms = hms_avr_guard_advance_ms;
        hms_avr_fixture.step_advance_ms = hms_avr_step_advance_ms;
        if (hms_avr_reset_receive != 0u) {
            hms_endpoint_link_reset_receive(&hms_avr_link);
            hms_avr_reset_receive = 0;
        }
        if (hms_avr_set_receive_budget != 0u) {
            hms_avr_budget_result = hms_endpoint_link_set_receive_budget(
                &hms_avr_link, hms_avr_receive_budget_ms);
            hms_avr_set_receive_budget = 0;
        }
        hms_endpoint_link_check_deadline(&hms_avr_link, hms_avr_fixture.clock_tick);
        if (hms_avr_input_ready != 0u) {
            hms_endpoint_link_feed(&hms_avr_link, &hms_avr_endpoint,
                hms_avr_input, hms_avr_fixture.clock_tick, hms_avr_fixture.platform_flags);
            hms_avr_input_ready = 0;
        }
        hms_endpoint_poll(&hms_avr_endpoint, hms_avr_fixture.clock_tick,
                          hms_avr_fixture.platform_flags);
        if (hms_avr_output_ready == 0u &&
                hms_endpoint_link_next(&hms_avr_link, &hms_avr_next_byte) != 0u) {
            hms_avr_output = hms_avr_next_byte;
            hms_avr_output_ready = 1;
        }
    }
}
