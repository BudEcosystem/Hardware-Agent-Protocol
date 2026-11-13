/* BHMS-Compact hardware abstraction layer.
 *
 * A port supplies one const bhms_hal. uart_read, uart_write and millis are
 * mandatory; the others are optional (NULL). Hooks must be bounded and must not
 * call back into the library.
 * Thread-safety: an endpoint is single-owner; call bhms_poll and every other
 * bhms_* function from one context (or serialise them).
 */
#ifndef BHMS_HAL_H
#define BHMS_HAL_H
#include <stddef.h>
#include <stdint.h>

typedef struct bhms_hal {
    void *ctx;
    /* Return the next received byte (0..255) or -1 when none is pending.
     * Non-blocking. On UART framing/overrun errors drop the byte(s); the frame
     * deadline resynchronises. */
    int (*uart_read)(void *ctx);
    /* Transmit n bytes; may block until queued. */
    void (*uart_write)(void *ctx, const uint8_t *buf, size_t n);
    /* Free-running millisecond counter (wraps at 2^32). */
    uint32_t (*millis)(void *ctx);
    /* Hardware stop input: nonzero while asserted. NULL when there is none.
     * Polled by bhms_poll on every call. The HAL MUST latch the asserting edge
     * (from a pin-change ISR or a hardware capture) and keep reporting nonzero
     * until it has been read once: a pulse shorter than one poll interval, or
     * one that arrives during a long callback, must not be lost. The endpoint
     * cannot do this itself; it only sees what this hook returns. */
    int (*stop_pin)(void *ctx);
    /* Persistent boot counter (EEPROM/flash). epoch_load returns 0 and stores
     * the last value (erased 0xFFFFFFFF must be reported as 0) or nonzero when
     * the store is unusable. epoch_store returns 0 once the value is durable.
     * Both NULL => PERSISTENT_EPOCH is not advertised (BHMS-CMP-020). */
    int (*epoch_load)(void *ctx, uint32_t *epoch);
    int (*epoch_store)(void *ctx, uint32_t epoch);
} bhms_hal;

#endif
