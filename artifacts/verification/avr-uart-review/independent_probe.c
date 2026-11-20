/* Original independent host-only review probe. No target execution. */
#include "protocol/platform/avr_uart.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static hms_avr_uart rx;
static hms_frame_parser parser;
static uint8_t mask, status, byte, available;
static uint8_t saved_masks[8];
static unsigned nesting, checks, status_reads, data_reads, resets;
static unsigned feed_hook, restore_hook;
static unsigned nested_irq;
static const char wire[] = "7e484d0101000000000000000000000000000000000e2a7e";

#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "independent check line %u: %s\n", (unsigned)__LINE__, #x); \
    exit(1); } } while (0)

static void arrival(uint8_t value, uint8_t flags);

uint8_t hms_avr_uart_probe_save_cli(void) {
    uint8_t saved = mask;
    CHECK(nesting < sizeof(saved_masks));
    saved_masks[nesting++] = saved;
    mask &= 0x7fu;
    return saved;
}

void hms_avr_uart_probe_restore(uint8_t saved) {
    CHECK(nesting && saved_masks[nesting - 1u] == saved);
    --nesting;
    mask = saved;
    if (restore_hook && !nesting && !nested_irq && (mask & 0x80u) &&
        !rx.foreground_active) {
        uint8_t prior = mask;
        restore_hook = 0;
        nested_irq = 1;
        mask &= 0x7fu;
        arrival(0xb7u, 0x84u);
        mask = prior;
        nested_irq = 0;
    }
}

uint8_t hms_avr_uart_probe_status(void) {
    CHECK(!(mask & 0x80u));
    ++status_reads;
    return status;
}

uint8_t hms_avr_uart_probe_data(void) {
    CHECK(!(mask & 0x80u) && available && status_reads == data_reads + 1u);
    ++data_reads;
    available = 0;
    return byte;
}

void __real_hms_frame_reset(hms_frame_parser *p);
void __wrap_hms_frame_reset(hms_frame_parser *p) {
    /* Every driver reset must execute while the gate is still closed. */
    CHECK(p == &parser && rx.foreground_active && rx.loss && !(mask & 0x80u));
    ++resets;
    __real_hms_frame_reset(p);
    CHECK(rx.loss && !p->active && !p->length && !p->escaped && !p->discarding);
}

hms_frame_result hms_avr_uart_probe_feed(hms_frame_parser *p, uint8_t value) {
    hms_frame_result result;
    CHECK(p == &parser && rx.foreground_active);
    result = hms_frame_feed(p, value);
    if (feed_hook) {
        unsigned hook = feed_hook;
        feed_hook = 0;
        CHECK(mask & 0x80u);
        if (hook == 1u) arrival(0xe3u, 0x98u);
        if (hook == 2u) {
            hms_avr_uart_event nested;
            hms_frame_result nested_frame = HMS_FRAME_READY;
            CHECK(hms_avr_uart_frame_step(&rx, p, &nested, &nested_frame) == HMS_AVR_UART_BUSY);
            CHECK(nested_frame == HMS_FRAME_NONE && rx.loss == HMS_AVR_UART_REENTRY);
        }
    }
    return result;
}

static void arrival(uint8_t value, uint8_t flags) {
    byte = value; status = flags; available = (uint8_t)((flags & 0x80u) != 0u);
    status_reads = data_reads = 0;
    hms_avr_uart_receive(&rx);
    CHECK(status_reads == 1u);
    CHECK(data_reads == ((flags & 0x80u) ? 1u : 0u));
    CHECK(!available);
}

static void clean(void) {
    CHECK(!nesting);
    mask = 0x80u; available = 0; feed_hook = restore_hook = nested_irq = 0;
    status_reads = data_reads = 0;
    hms_avr_uart_init(&rx);
    __real_hms_frame_reset(&parser);
    CHECK(!rx.count && !rx.loss && !rx.foreground_active && !rx.receive_active);
}

static hms_avr_uart_result step(hms_avr_uart_event *event, hms_frame_result *frame) {
    hms_avr_uart_result result = hms_avr_uart_frame_step(&rx, &parser, event, frame);
    CHECK(!nesting && !rx.foreground_active && !rx.receive_active);
    CHECK(rx.count <= HMS_AVR_UART_CAPACITY && (!rx.loss || !rx.count));
    return result;
}

static void before_close(void) {
    size_t i;
    for (i = 0; i < strlen(wire); i += 2u) {
        unsigned value;
        hms_avr_uart_event event; hms_frame_result frame;
        CHECK(sscanf(wire + i, "%2x", &value) == 1);
        arrival((uint8_t)value, 0xe2u);
        if (i + 2u < strlen(wire))
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && frame == HMS_FRAME_NONE);
    }
}

static void all_status_patterns(void) {
    unsigned flags;
    for (flags = 0; flags < 256u; ++flags) {
        hms_avr_uart_event event; hms_frame_result frame;
        unsigned expected_errors = ((flags & 0x10u) >> 4) | ((flags & 0x08u) >> 2) | (flags & 0x04u);
        clean();
        arrival(0xc5u, (uint8_t)flags);
        if (!(flags & 0x80u)) {
            CHECK(step(&event, &frame) == HMS_AVR_UART_EMPTY);
            CHECK(!rx.loss && frame == HMS_FRAME_NONE && !event.byte_valid);
        } else if (expected_errors) {
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS);
            CHECK(event.loss == expected_errors && event.byte_valid && event.byte == 0xc5u &&
                  event.status == flags && frame == HMS_FRAME_NONE);
        } else {
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE);
            CHECK(event.byte_valid && event.byte == 0xc5u && event.status == flags && !event.loss);
        }
    }
}

static void gate_publication_and_later_loss(void) {
    hms_avr_uart_event event; hms_frame_result frame;
    unsigned before;
    clean();
    (void)hms_frame_feed(&parser, 0x7eu);
    (void)hms_frame_feed(&parser, 0x7du);
    arrival(0x65u, 0x90u);
    arrival(0x66u, 0x8cu);
    CHECK(rx.loss == 7u && !rx.count);
    before = resets; restore_hook = 1;
    CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
    CHECK(resets == before + 1u && event.byte == 0x65u && event.status == 0x90u && event.loss == 7u);
    CHECK(rx.loss == HMS_AVR_UART_PARITY_ERROR && !parser.active);
    CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && event.byte == 0xb7u && event.loss == HMS_AVR_UART_PARITY_ERROR);
    CHECK(!rx.loss && !parser.active);
}

static void frame_linearization(void) {
    hms_avr_uart_event event; hms_frame_result frame;
    unsigned mode;
    for (mode = 1; mode <= 3u; ++mode) {
        clean(); before_close();
        if (mode < 3u) feed_hook = mode;
        else restore_hook = 1;
        if (mode < 3u) {
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
            CHECK(!parser.active && !rx.loss);
        } else {
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && frame == HMS_FRAME_READY);
            CHECK(parser.raw[0] == 'H' && parser.raw[1] == 'M' && parser.raw[2] == 1u &&
                  parser.raw[20] == 0x0eu && parser.raw[21] == 0x2au);
            CHECK(rx.loss == HMS_AVR_UART_PARITY_ERROR);
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
        }
    }
}

static void disabled_entry_and_gate(void) {
    unsigned bits;
    for (bits = 0; bits < 256u; ++bits) {
        hms_avr_uart_event event; hms_frame_result frame;
        clean(); mask = (uint8_t)bits;
        arrival(0x7eu, 0x80u);
        CHECK(mask == bits);
        CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && mask == bits);
        hms_avr_uart_discontinuity(&rx);
        CHECK(mask == bits);
        CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && mask == bits);
    }
}

int main(void) {
    all_status_patterns();
    gate_publication_and_later_loss();
    frame_linearization();
    disabled_entry_and_gate();
    printf("{\"status\":\"pass\",\"checks\":%u,\"status_patterns\":256,\"mask_patterns\":256,"
           "\"reset_gate_observations\":%u,\"frame_boundary_cases\":3,\"target_executed\":false}\n",
           checks, resets);
    return 0;
}
