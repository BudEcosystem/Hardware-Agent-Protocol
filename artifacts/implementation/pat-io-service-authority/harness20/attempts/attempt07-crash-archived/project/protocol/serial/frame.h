#ifndef HMS_SERIAL_FRAME_H
#define HMS_SERIAL_FRAME_H
#include <stddef.h>
#include <stdint.h>

#define HMS_FRAME_HEADER 20u
#define HMS_FRAME_PAYLOAD 192u
#define HMS_FRAME_RAW (HMS_FRAME_HEADER + HMS_FRAME_PAYLOAD + 2u)
#define HMS_FRAME_WIRE_MAX (2u * HMS_FRAME_RAW + 2u)

typedef struct {
    uint8_t raw[HMS_FRAME_RAW];
    uint16_t length;
    uint8_t active;
    uint8_t escaped;
    uint8_t discarding;
} hms_frame_parser;

typedef enum { HMS_FRAME_NONE, HMS_FRAME_READY, HMS_FRAME_INVALID,
               HMS_FRAME_OVERFLOW } hms_frame_result;

/* No allocator, I/O, clock, authentication, retransmission or actuation.
 * On READY, raw contains a validated header/payload/FCS. Consume synchronously
 * before the next feed call. No concurrent/reentrant use of one parser.
 * An external absolute receive deadline/UART error must call reset.
 */
void hms_frame_reset(hms_frame_parser *parser);
hms_frame_result hms_frame_feed(hms_frame_parser *parser, uint8_t byte);
#endif
