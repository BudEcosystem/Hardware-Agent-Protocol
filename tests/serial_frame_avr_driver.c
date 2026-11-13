/* Original HMS build-only harness. Never flashed or executed on a target.
 * Volatile mailboxes keep byte input and result externally observable without
 * linking a UART driver, Arduino core, stdio, timers or device callbacks.
 * This is not endpoint firmware and does not validate target runtime behavior.
 */
#include "../protocol/serial/frame.h"

hms_frame_parser hms_avr_parser;
volatile uint8_t hms_avr_input;
volatile uint8_t hms_avr_event;

_Static_assert(sizeof(hms_frame_parser) == 219u, "ATmega328P ABI changed");
_Static_assert(sizeof(unsigned int) == 2u, "Expected AVR 16-bit int");
_Static_assert(sizeof(unsigned long) == 4u, "Expected AVR 32-bit long");

int main(void) {
    hms_frame_reset(&hms_avr_parser);
    for (;;) {
        hms_avr_event = (uint8_t)hms_frame_feed(&hms_avr_parser, hms_avr_input);
    }
}
