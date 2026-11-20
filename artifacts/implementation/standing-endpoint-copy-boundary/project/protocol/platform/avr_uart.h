#ifndef HMS_AVR_UART_H
#define HMS_AVR_UART_H

#include <stdint.h>
#include "../serial/frame.h"

#define HMS_AVR_UART_CAPACITY 16u

/* Loss reasons are cumulative while the gate is closed. DOR is one or more
 * lost serial characters; these bits do not count lost bytes or frames. */
#define HMS_AVR_UART_FRAME_ERROR  UINT8_C(0x01)
#define HMS_AVR_UART_DATA_OVERRUN UINT8_C(0x02)
#define HMS_AVR_UART_PARITY_ERROR UINT8_C(0x04)
#define HMS_AVR_UART_RING_FULL    UINT8_C(0x08)
#define HMS_AVR_UART_REENTRY      UINT8_C(0x10)
#define HMS_AVR_UART_EXTERNAL_LOSS UINT8_C(0x20)

typedef enum {
    HMS_AVR_UART_EMPTY, HMS_AVR_UART_BYTE, HMS_AVR_UART_LOSS,
    HMS_AVR_UART_BUSY, HMS_AVR_UART_BAD_ARGUMENT
} hms_avr_uart_result;

typedef struct {
    uint8_t byte;
    uint8_t status; /* Exact UCSR0A snapshot preceding this byte's UDR0 read. */
    uint8_t byte_valid;
    uint8_t loss;
} hms_avr_uart_event;

typedef struct {
    volatile uint8_t bytes[HMS_AVR_UART_CAPACITY];
    volatile uint8_t status[HMS_AVR_UART_CAPACITY];
    volatile uint8_t head, tail, count;
    volatile uint8_t loss, trigger_byte, trigger_status, trigger_valid;
    volatile uint8_t foreground_active, receive_active;
} hms_avr_uart;

/* Original receive-only ATmega328P USART0 boundary. No vector, baud/pin/mode
 * setup, peripheral enable/disable, TX, polling wait, allocation or clock.
 * The platform exclusively owns USART0 reception and installs an RX ISR that
 * calls receive() once. It must configure and preserve an eight-data-bit
 * asynchronous link before reception; parity/stop/baud and interrupt service
 * bounds are installation obligations, not qualified by this module. No other
 * code may read UDR0 or alter the queue, parser, or RX configuration. A change
 * of link/configuration must be reported with discontinuity() before reuse.
 * The 9-bit/multiprocessor receive protocol is not implemented.
 *
 * init() is only for startup while the receiver/ISR and foreground are stopped.
 * It initializes software state, never flushes hardware or resets a parser.
 * receive() uses one saved-SREG critical section, at most one UCSR0A read and
 * one UDR0 read. It drains a received byte even while the loss gate is closed.
 * Every FE/DOR/UPE or full-ring event closes the gate and discards the queue.
 * Subsequent received bytes are discarded until frame_step() acknowledges it.
 *
 * frame_step() consumes at most one byte. Its parser feed/CRC runs with the
 * caller's prior interrupt state restored. A loss during feed suppresses the
 * frame result. Loss acknowledgment snapshots its event, resets the parser,
 * then reopens the gate atomically under the saved interrupt mask. A new loss
 * after reopening remains pending for the next call. A clean FRAME_READY is
 * linearized at the final masked loss check: a subsequent loss does not revoke
 * that already-complete frame. Consume READY bytes synchronously before the
 * next step, as required by hms_frame_feed. A LOSS event reports the triggering
 * byte/status if available; its loss bits can also include later gated errors.
 * Discarded queue bytes and total lost byte count are deliberately not guessed.
 *
 * One foreground owner; valid non-overlapping rx/parser/output objects. Reentry
 * closes the gate and returns BUSY without reentering/resetting the parser;
 * the outer call observes the loss. All access windows save/restore SREG; an
 * entry with interrupts disabled keeps them disabled, including during CRC.
 * The caller owns that latency. init() and object lifetime are not reentrant.
 *
 * This resets TRANSPORT FRAME ASSEMBLY ONLY. It never clears endpoint boot,
 * context, operation, fence, receipt, cancellation or uncertain-effect state.
 * Absolute receive deadlines, fair service budgets, link-loss policy, UART
 * timing, stack/ISR nesting and independent physical stop remain platform work.
 */
void hms_avr_uart_init(hms_avr_uart *rx);
void hms_avr_uart_receive(hms_avr_uart *rx);
void hms_avr_uart_discontinuity(hms_avr_uart *rx);
hms_avr_uart_result hms_avr_uart_frame_step(hms_avr_uart *rx,
    hms_frame_parser *parser, hms_avr_uart_event *event,
    hms_frame_result *frame_result);
/* Same continuity gate with an optional bounded foreground hook immediately
 * before parser feed, after restoring SREG. Hook may reset that parser to apply
 * an absolute assembly deadline; it must not feed/dispatch/reenter. A loss
 * during hook/feed still suppresses READY at the final masked check. */
hms_avr_uart_result hms_avr_uart_frame_step_hook(hms_avr_uart *rx,
    hms_frame_parser *parser, hms_avr_uart_event *event,
    hms_frame_result *frame_result, void (*before_feed)(void *, uint8_t), void *user);

#endif
