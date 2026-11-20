#ifndef HMS_AVR_USART_H
#define HMS_AVR_USART_H
#include <stdint.h>
#include "../endpoint/link.h"

/* Fixed 8N1 asynchronous USART0 owner. Init/start are startup-only, while
 * ordinary effects, RX ISR and all other USART users are inhibited. A fresh
 * hardware reset/quiescent transmitter is a caller obligation; register bits
 * alone do not prove an earlier owner's shift register is empty. No live
 * reconfiguration, blocking flush, TX ISR, extra ring or reset-on-error exists.
 * UBRR is an explicit 12-bit divider, not an assertion of measured baud. */
typedef struct {
    uint16_t ubrr;
    uint8_t u2x, started, fault, wrote, active;
} hms_avr_usart;
typedef enum {
    HMS_AVR_USART_IDLE, HMS_AVR_USART_SENT, HMS_AVR_USART_WAIT,
    HMS_AVR_USART_FAULT, HMS_AVR_USART_BUSY
} hms_avr_usart_result;

void hms_avr_usart_init(hms_avr_usart *port);
uint8_t hms_avr_usart_start(hms_avr_usart *port, uint16_t ubrr, uint8_t double_speed);
/* Returns false and latches a fault if installed configuration/ownership drifts.
 * This is not independent detection of arbitrary same-UID/native tampering. */
uint8_t hms_avr_usart_current(hms_avr_usart *port);
/* At most one link_next and one UDR write, only if UDRE is set. No wait loop.
 * UDR write precedes TXC W1C in a saved-SREG critical window. Error/status bits
 * are written zero; the installed U2X value is preserved and MPCM is disabled.
 * SENT means handed to UART, never received by the peer or physically acted. */
hms_avr_usart_result hms_avr_usart_transmit(hms_avr_usart *port, hms_endpoint_link *link);
/* True only when software frame is empty and (no byte was sent since fresh
 * startup, or TXC reports entire hardware frame/buffer drained). Not a peer
 * acknowledgment, old-host-queue purge, endpoint quiescence or permission to
 * reconfigure/reset. One foreground owner serializes all port/link APIs. */
uint8_t hms_avr_usart_drained(hms_avr_usart *port, const hms_endpoint_link *link);
#endif
