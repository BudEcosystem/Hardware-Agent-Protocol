#include "avr_uart.h"
#include <stddef.h>

#if defined(HMS_AVR_UART_TEST)
/* Original host register model. This does not emulate silicon or cycle timing. */
extern uint8_t hms_avr_uart_probe_save_cli(void);
extern void hms_avr_uart_probe_restore(uint8_t saved);
extern uint8_t hms_avr_uart_probe_status(void);
extern uint8_t hms_avr_uart_probe_data(void);
extern hms_frame_result hms_avr_uart_probe_feed(hms_frame_parser *, uint8_t);
#define save_cli hms_avr_uart_probe_save_cli
#define restore hms_avr_uart_probe_restore
#define read_status hms_avr_uart_probe_status
#define read_data hms_avr_uart_probe_data
#define feed hms_avr_uart_probe_feed
#else
#if !defined(__AVR_ATmega328P__)
#error This register adapter is only reviewed for ATmega328P
#endif
#include <avr/io.h>
#include <avr/interrupt.h>
_Static_assert(_SFR_MEM_ADDR(UCSR0A) == 0xc0 && _SFR_MEM_ADDR(UDR0) == 0xc6,
               "Reviewed USART0 addresses");
_Static_assert(RXC0 == 7 && FE0 == 4 && DOR0 == 3 && UPE0 == 2,
               "Reviewed buffered receive status bits");
static uint8_t save_cli(void) { uint8_t saved = SREG; cli(); return saved; }
static void restore(uint8_t saved) { SREG = saved; __asm__ __volatile__("" ::: "memory"); }
static uint8_t read_status(void) { return UCSR0A; }
static uint8_t read_data(void) { return UDR0; }
#define feed hms_frame_feed
#endif

/* Called only with interrupts masked. Captures the first cause and merges
 * later hardware errors without pretending they belong to the trigger byte. */
static void lose(hms_avr_uart *rx, uint8_t reason, uint8_t byte,
                 uint8_t status, uint8_t valid) {
    if (rx->loss == 0u) {
        rx->trigger_byte = byte;
        rx->trigger_status = status;
        rx->trigger_valid = valid;
        rx->head = 0; rx->tail = 0; rx->count = 0;
    }
    rx->loss = (uint8_t)(rx->loss | reason);
}

void hms_avr_uart_init(hms_avr_uart *rx) {
    uint8_t saved;
    if (rx == NULL) return;
    saved = save_cli();
    rx->head = 0; rx->tail = 0; rx->count = 0; rx->loss = 0;
    rx->trigger_byte = 0; rx->trigger_status = 0; rx->trigger_valid = 0;
    rx->foreground_active = 0; rx->receive_active = 0;
    restore(saved);
}

void hms_avr_uart_receive(hms_avr_uart *rx) {
    uint8_t saved, status, byte, errors = 0, head;
    if (rx == NULL) return;
    saved = save_cli();
    if (rx->receive_active != 0u) {
        lose(rx, HMS_AVR_UART_REENTRY, 0, 0, 0);
        restore(saved); return;
    }
    rx->receive_active = 1;
    status = read_status();
    if (1) {
        /* UDR0 advances the receive FIFO and its buffered FE/DOR/UPE flags. */
        byte = read_data();
        if ((status & UINT8_C(0x10)) != 0u) errors |= HMS_AVR_UART_FRAME_ERROR;
        if ((status & UINT8_C(0x08)) != 0u) errors |= HMS_AVR_UART_DATA_OVERRUN;
        if ((status & UINT8_C(0x04)) != 0u) errors |= HMS_AVR_UART_PARITY_ERROR;
        if (rx->loss != 0u || errors != 0u) {
            lose(rx, errors, byte, status, 1);
        } else if (rx->count == HMS_AVR_UART_CAPACITY) {
            lose(rx, HMS_AVR_UART_RING_FULL, byte, status, 1);
        } else {
            head = rx->head;
            rx->bytes[head] = byte; rx->status[head] = status;
            rx->head = (uint8_t)((head + 1u) & (HMS_AVR_UART_CAPACITY - 1u));
            rx->count = (uint8_t)(rx->count + 1u);
        }
    }
    rx->receive_active = 0;
    restore(saved);
}

void hms_avr_uart_discontinuity(hms_avr_uart *rx) {
    uint8_t saved;
    if (rx == NULL) return;
    saved = save_cli();
    lose(rx, HMS_AVR_UART_EXTERNAL_LOSS, 0, 0, 0);
    restore(saved);
}

/* Parser reset must finish before reopening. Interrupts remain masked here. */
static void acknowledge(hms_avr_uart *rx, hms_frame_parser *parser,
                        hms_avr_uart_event *event) {
    event->byte = rx->trigger_byte; event->status = rx->trigger_status;
    event->byte_valid = rx->trigger_valid; event->loss = rx->loss;
    hms_frame_reset(parser);
    rx->loss = 0; rx->trigger_valid = 0;
}

hms_avr_uart_result hms_avr_uart_frame_step(hms_avr_uart *rx,
    hms_frame_parser *parser, hms_avr_uart_event *event,
    hms_frame_result *frame_result) {
    uint8_t saved, tail;
    hms_frame_result result;
    if (rx == NULL || parser == NULL || event == NULL || frame_result == NULL)
        return HMS_AVR_UART_BAD_ARGUMENT;
    *frame_result = HMS_FRAME_NONE;
    event->byte = 0; event->status = 0; event->byte_valid = 0; event->loss = 0;
    saved = save_cli();
    if (rx->foreground_active != 0u) {
        lose(rx, HMS_AVR_UART_REENTRY, 0, 0, 0);
        restore(saved); return HMS_AVR_UART_BUSY;
    }
    rx->foreground_active = 1;
    if (rx->loss != 0u) {
        acknowledge(rx, parser, event);
        rx->foreground_active = 0;
        restore(saved); return HMS_AVR_UART_LOSS;
    }
    if (rx->count == 0u) {
        rx->foreground_active = 0;
        restore(saved); return HMS_AVR_UART_EMPTY;
    }
    tail = rx->tail;
    event->byte = rx->bytes[tail]; event->status = rx->status[tail];
    event->byte_valid = 1;
    rx->tail = (uint8_t)((tail + 1u) & (HMS_AVR_UART_CAPACITY - 1u));
    rx->count = (uint8_t)(rx->count - 1u);
    restore(saved);
    result = feed(parser, event->byte);
    saved = save_cli();
    if (rx->loss != 0u) {
        acknowledge(rx, parser, event);
        rx->foreground_active = 0;
        restore(saved); return HMS_AVR_UART_LOSS;
    }
    *frame_result = result;
    rx->foreground_active = 0;
    restore(saved);
    return HMS_AVR_UART_BYTE;
}
