#include "../protocol/platform/avr_uart.h"

#if defined(HMS_AVR_UART_TEST)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long checks;
static unsigned cases, fault_cases, wrap_cases, race_cases;
#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "check failed line %u: %s\n", (unsigned)__LINE__, #x); exit(1); } } while (0)

static hms_avr_uart rx;
static hms_frame_parser parser;
static uint8_t sreg, pending, hw_byte, hw_status, status_seen;
static unsigned saves, restores, status_reads, data_reads, feeds, depth;
static uint8_t saved_stack[8];
static unsigned receive_hook, feed_hook, restore_hook, save_hook;
static unsigned irq_active;
static uint8_t feed_sreg;
static const char *const WIRE[] = {
    "7e484d0101000000000000000000000000000000000e2a7e",
    "7e484d01020001010203040506070801020304000568656c6c6f6dfd7e",
    "7e484d0103000200000000000000090000001100067d5e7d5d00ff1113aaa87e"
};

static void arrive(uint8_t byte, uint8_t status);
static void irq(uint8_t byte, uint8_t status) {
    uint8_t prior = sreg;
    CHECK((sreg & 0x80u) != 0u);
    sreg = (uint8_t)(sreg & 0x7fu); ++irq_active;
    arrive(byte, status);
    --irq_active; sreg = prior; /* Models saved ISR state/RETI, not its cycles. */
}

uint8_t hms_avr_uart_probe_save_cli(void) {
    uint8_t prior = sreg;
    ++saves;
    if (save_hook != 0u) {
        --save_hook;
        if (save_hook == 0u) irq(0xa1, 0x90);
    }
    CHECK(depth < sizeof(saved_stack));
    saved_stack[depth++] = prior;
    sreg = (uint8_t)(sreg & 0x7fu);
    return prior;
}

void hms_avr_uart_probe_restore(uint8_t saved) {
    CHECK(depth > 0u && saved_stack[depth - 1u] == saved);
    --depth; ++restores; sreg = saved;
    if (irq_active == 0u && depth == 0u && (sreg & 0x80u) != 0u &&
        ((restore_hook == 1u && rx.foreground_active != 0u) ||
         (restore_hook == 2u && rx.foreground_active == 0u))) {
        restore_hook = 0;
        irq(0xa2, 0x84);
    }
}

uint8_t hms_avr_uart_probe_status(void) {
    uint8_t result;
    CHECK((sreg & 0x80u) == 0u && rx.receive_active == 1u);
    ++status_reads;
    result = pending ? hw_status : 0;
    status_seen = pending;
    if (receive_hook == 1u) {
        receive_hook = 0;
        hms_avr_uart_receive(&rx);
    }
    return result;
}

uint8_t hms_avr_uart_probe_data(void) {
    uint8_t result = hw_byte;
    CHECK((sreg & 0x80u) == 0u && pending && status_seen);
    ++data_reads; pending = 0; status_seen = 0;
    if (receive_hook == 2u) {
        receive_hook = 0;
        hms_avr_uart_receive(&rx);
    }
    return result;
}

hms_frame_result hms_avr_uart_probe_feed(hms_frame_parser *p, uint8_t byte) {
    unsigned mode = feed_hook;
    hms_frame_result result;
    feed_hook = 0; ++feeds; feed_sreg = sreg;
    CHECK(rx.foreground_active == 1u);
    if (mode == 1u) irq(0xa3, 0x98);
    if (mode == 3u) {
        hms_avr_uart_event nested;
        hms_frame_result frame = HMS_FRAME_READY;
        CHECK(hms_avr_uart_frame_step(&rx, p, &nested, &frame) == HMS_AVR_UART_BUSY);
        CHECK(frame == HMS_FRAME_NONE && rx.foreground_active == 1u);
    }
    if (mode == 4u) {
        unsigned i;
        for (i = 0; i <= HMS_AVR_UART_CAPACITY; ++i) irq((uint8_t)i, 0x80);
    }
    if (mode == 5u) hms_avr_uart_discontinuity(&rx);
    if (mode == 6u) irq(0x42, 0xe2);
    result = hms_frame_feed(p, byte);
    if (mode == 2u) irq(0xa4, 0x90);
    return result;
}

static void arrive(uint8_t byte, uint8_t status) {
    unsigned before_status = status_reads, before_data = data_reads;
    CHECK(!pending && (status & 0x80u) != 0u);
    hw_byte = byte; hw_status = status; pending = 1; status_seen = 0;
    hms_avr_uart_receive(&rx);
    CHECK(!pending && status_reads == before_status + 1u && data_reads == before_data + 1u);
    CHECK(rx.head < HMS_AVR_UART_CAPACITY && rx.tail < HMS_AVR_UART_CAPACITY &&
          rx.count <= HMS_AVR_UART_CAPACITY && (rx.loss == 0u || rx.count == 0u));
}

static void reset(void) {
    CHECK(depth == 0u);
    pending = status_seen = 0;
    receive_hook = feed_hook = restore_hook = save_hook = irq_active = 0;
    sreg = 0x80;
    hms_avr_uart_init(&rx); hms_frame_reset(&parser);
    CHECK(rx.count == 0u && rx.loss == 0u && !rx.foreground_active && !rx.receive_active);
}

static hms_avr_uart_result step(hms_avr_uart_event *event, hms_frame_result *frame) {
    unsigned old_feeds = feeds;
    hms_avr_uart_result result = hms_avr_uart_frame_step(&rx, &parser, event, frame);
    CHECK(feeds <= old_feeds + 1u && depth == 0u && !rx.foreground_active);
    CHECK(rx.head < HMS_AVR_UART_CAPACITY && rx.tail < HMS_AVR_UART_CAPACITY &&
          rx.count <= HMS_AVR_UART_CAPACITY && (rx.loss == 0u || rx.count == 0u));
    return result;
}

static unsigned bytes_from_hex(const char *hex, uint8_t *out) {
    unsigned i, length = (unsigned)strlen(hex) / 2u;
    for (i = 0; i < length; ++i) {
        unsigned value;
        CHECK(sscanf(hex + 2u * i, "%2x", &value) == 1);
        out[i] = (uint8_t)value;
    }
    return length;
}

static unsigned feed_wire(const char *hex) {
    uint8_t bytes[HMS_FRAME_WIRE_MAX];
    unsigned i, length = bytes_from_hex(hex, bytes), ready = 0;
    for (i = 0; i < length; ++i) {
        hms_avr_uart_event event;
        hms_frame_result frame;
        arrive(bytes[i], 0xe2);
        CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE);
        CHECK(event.byte == bytes[i] && event.status == 0xe2 && event.byte_valid == 1u && event.loss == 0u);
        if (frame == HMS_FRAME_READY) ++ready;
        else CHECK(frame == HMS_FRAME_NONE);
    }
    return ready;
}

static void ready_except_close(void) {
    uint8_t bytes[HMS_FRAME_WIRE_MAX];
    unsigned i, length = bytes_from_hex(WIRE[0], bytes);
    for (i = 0; i + 1u < length; ++i) {
        hms_avr_uart_event event; hms_frame_result frame;
        arrive(bytes[i], 0x80);
        CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && frame == HMS_FRAME_NONE);
    }
    arrive(bytes[length - 1u], 0x80);
}

static void empty_and_arguments(void) {
    hms_avr_uart_event event = {1, 2, 3, 4};
    hms_frame_result frame = HMS_FRAME_READY;
    unsigned before_status, before_data;
    reset(); ++cases;
    before_status = status_reads; before_data = data_reads;
    hms_avr_uart_init(NULL); hms_avr_uart_receive(NULL); hms_avr_uart_discontinuity(NULL);
    CHECK(hms_avr_uart_frame_step(NULL, &parser, &event, &frame) == HMS_AVR_UART_BAD_ARGUMENT);
    CHECK(hms_avr_uart_frame_step(&rx, NULL, &event, &frame) == HMS_AVR_UART_BAD_ARGUMENT);
    CHECK(hms_avr_uart_frame_step(&rx, &parser, NULL, &frame) == HMS_AVR_UART_BAD_ARGUMENT);
    CHECK(hms_avr_uart_frame_step(&rx, &parser, &event, NULL) == HMS_AVR_UART_BAD_ARGUMENT);
    CHECK(status_reads == before_status && data_reads == before_data);
    hms_avr_uart_receive(&rx);
    CHECK(status_reads == before_status + 1u && data_reads == before_data);
    CHECK(step(&event, &frame) == HMS_AVR_UART_EMPTY && frame == HMS_FRAME_NONE);
    CHECK(!event.byte_valid && event.loss == 0u);
}

static void sreg_patterns(void) {
    unsigned i;
    ++cases;
    for (i = 0; i < 256u; ++i) {
        hms_avr_uart_event event; hms_frame_result frame;
        reset(); sreg = (uint8_t)i;
        arrive((uint8_t)i, 0xe2);
        CHECK(sreg == i);
        CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && event.byte == i);
        CHECK(sreg == i && feed_sreg == i);
        hms_avr_uart_discontinuity(&rx);
        CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && sreg == i);
    }
}

static void ring_positions(void) {
    unsigned offset, length, i;
    ++cases;
    for (offset = 0; offset < HMS_AVR_UART_CAPACITY; ++offset) {
        for (length = 0; length <= HMS_AVR_UART_CAPACITY; ++length) {
            hms_avr_uart_event event; hms_frame_result frame;
            reset(); ++wrap_cases;
            for (i = 0; i < offset; ++i) {
                arrive(0x20, 0x80); CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE);
            }
            CHECK(rx.head == offset && rx.tail == offset);
            for (i = 0; i < length; ++i) arrive((uint8_t)i, (uint8_t)(0x80u | ((i & 3u) << 5)));
            CHECK(rx.count == length);
            for (i = 0; i < length; ++i) {
                CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && event.byte == i);
                CHECK(event.status == (uint8_t)(0x80u | ((i & 3u) << 5)) && event.loss == 0u);
            }
            CHECK(step(&event, &frame) == HMS_AVR_UART_EMPTY);
        }
    }
}

static void all_hardware_faults(void) {
    unsigned combination, byte;
    ++cases;
    for (combination = 1; combination < 8u; ++combination) {
        uint8_t status = (uint8_t)(0x80u | ((combination & 1u) << 4) |
                                  ((combination & 2u) << 2) | (combination & 4u));
        for (byte = 0; byte < 256u; ++byte) {
            hms_avr_uart_event event; hms_frame_result frame;
            reset(); ++fault_cases;
            (void)hms_frame_feed(&parser, 0x7e); (void)hms_frame_feed(&parser, 0x48);
            arrive(0x4d, 0x80); /* Conservatively discarded queued byte. */
            arrive((uint8_t)byte, status);
            CHECK(rx.loss == combination && rx.count == 0u);
            arrive(0x7e, 0x80); /* Gated data/flags never enter the parser. */
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
            CHECK(event.byte == byte && event.status == status && event.byte_valid && event.loss == combination);
            CHECK(!parser.active && !parser.length && !parser.escaped && !parser.discarding && !rx.loss);
        }
    }
    CHECK(feed_wire(WIRE[0]) == 1u);
}

static void overflow_gate(void) {
    unsigned offset, i;
    ++cases;
    for (offset = 0; offset < HMS_AVR_UART_CAPACITY; ++offset) {
        hms_avr_uart_event event; hms_frame_result frame;
        reset();
        for (i = 0; i < offset; ++i) {
            arrive(0x21, 0x80); CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE);
        }
        for (i = 0; i < HMS_AVR_UART_CAPACITY; ++i) arrive((uint8_t)i, 0x80);
        CHECK(rx.count == HMS_AVR_UART_CAPACITY && !rx.loss);
        arrive(0xaf, 0xe2);
        CHECK(rx.count == 0u && rx.loss == HMS_AVR_UART_RING_FULL);
        for (i = 0; i < 257u; ++i) arrive((uint8_t)i, 0x80);
        arrive(0x55, 0x9c);
        CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS);
        CHECK(event.byte == 0xafu && event.status == 0xe2u && event.byte_valid);
        CHECK(event.loss == (HMS_AVR_UART_RING_FULL | 7u) && frame == HMS_FRAME_NONE);
        CHECK(step(&event, &frame) == HMS_AVR_UART_EMPTY);
        CHECK(feed_wire(WIRE[0]) == 1u);
    }
}

static void fault_at_every_frame_byte(void) {
    uint8_t bytes[HMS_FRAME_WIRE_MAX];
    unsigned vector, at, i;
    ++cases;
    for (vector = 0; vector < 3u; ++vector) {
        unsigned length = bytes_from_hex(WIRE[vector], bytes);
        for (at = 0; at < length; ++at) {
            reset();
            for (i = 0; i < length; ++i) {
                hms_avr_uart_event event; hms_frame_result frame;
                arrive(bytes[i], i == at ? 0x8c : 0x80);
                CHECK(step(&event, &frame) == (i == at ? HMS_AVR_UART_LOSS : HMS_AVR_UART_BYTE));
                CHECK(frame != HMS_FRAME_READY);
            }
            CHECK(feed_wire(WIRE[vector]) == 1u);
        }
    }
}

static void feed_races(void) {
    unsigned mode;
    ++cases;
    for (mode = 1; mode <= 6u; ++mode) {
        hms_avr_uart_event event; hms_frame_result frame;
        reset(); ready_except_close(); feed_hook = mode; ++race_cases;
        if (mode == 6u) {
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && frame == HMS_FRAME_READY);
            CHECK(rx.count == 1u && !rx.loss);
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && event.byte == 0x42u);
        } else {
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
            CHECK(event.loss != 0u && !parser.active && !rx.loss);
            CHECK(feed_wire(WIRE[0]) == 1u);
        }
    }
}

static void mask_boundary_races(void) {
    unsigned mode;
    ++cases;
    for (mode = 1; mode <= 4u; ++mode) {
        hms_avr_uart_event event; hms_frame_result frame;
        reset(); ready_except_close(); ++race_cases;
        if (mode == 1u) save_hook = 1;
        if (mode == 2u) restore_hook = 1;
        if (mode == 3u) save_hook = 2;
        if (mode == 4u) restore_hook = 2;
        if (mode == 4u) {
            CHECK(step(&event, &frame) == HMS_AVR_UART_BYTE && frame == HMS_FRAME_READY);
            CHECK(rx.loss == HMS_AVR_UART_PARITY_ERROR && parser.active);
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && !parser.active);
        } else {
            CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
            CHECK(!rx.loss && !parser.active);
        }
        CHECK(feed_wire(WIRE[0]) == 1u);
    }
}

static void fault_after_acknowledgment(void) {
    hms_avr_uart_event event; hms_frame_result frame;
    reset(); ++cases; ++race_cases;
    arrive(0x33, 0x90); restore_hook = 2;
    CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
    CHECK(event.loss == HMS_AVR_UART_FRAME_ERROR && event.byte == 0x33u);
    CHECK(rx.loss == HMS_AVR_UART_PARITY_ERROR);
    CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && frame == HMS_FRAME_NONE);
    CHECK(event.loss == HMS_AVR_UART_PARITY_ERROR && event.byte == 0xa2u);
    CHECK(!rx.loss && feed_wire(WIRE[0]) == 1u);
}

static void receive_reentry(void) {
    unsigned phase;
    ++cases;
    for (phase = 1; phase <= 2u; ++phase) {
        hms_avr_uart_event event; hms_frame_result frame;
        reset(); receive_hook = phase;
        arrive(0x44, 0x80);
        CHECK(rx.loss == HMS_AVR_UART_REENTRY && !rx.receive_active);
        CHECK(step(&event, &frame) == HMS_AVR_UART_LOSS && !event.byte_valid);
        CHECK(event.loss == HMS_AVR_UART_REENTRY && !rx.loss);
    }
}

static void bounded_flood(void) {
    uint32_t random = UINT32_C(0x1b8f2ad5);
    unsigned i;
    ++cases; reset();
    for (i = 0; i < 20000u; ++i) {
        hms_avr_uart_event event; hms_frame_result frame;
        random = random * UINT32_C(1664525) + UINT32_C(1013904223);
        if ((random & 7u) < 5u) {
            uint8_t errors = (random & 255u) == 0u ? 0x1cu : 0u;
            arrive((uint8_t)(random >> 16), (uint8_t)(0x80u | errors));
        } else if ((random & 7u) == 6u) {
            hms_avr_uart_discontinuity(&rx);
        } else {
            hms_avr_uart_result result = step(&event, &frame);
            CHECK(result == HMS_AVR_UART_BYTE || result == HMS_AVR_UART_EMPTY || result == HMS_AVR_UART_LOSS);
            if (result != HMS_AVR_UART_BYTE) CHECK(frame == HMS_FRAME_NONE);
        }
        CHECK(rx.count <= HMS_AVR_UART_CAPACITY && !rx.receive_active && !rx.foreground_active);
        CHECK(rx.loss == 0u || rx.count == 0u);
    }
}

static void full_valid_vectors(void) {
    unsigned i;
    ++cases; reset();
    for (i = 0; i < 3u; ++i) CHECK(feed_wire(WIRE[i]) == 1u);
    CHECK(parser.raw[0] == 'H' && parser.raw[1] == 'M' && parser.raw[2] == 1u);
    CHECK(parser.raw[20] == 0x7eu && parser.raw[21] == 0x7du);
    CHECK(saves == restores && depth == 0u);
}

int main(void) {
    empty_and_arguments(); sreg_patterns(); ring_positions(); all_hardware_faults();
    overflow_gate(); fault_at_every_frame_byte(); feed_races(); mask_boundary_races();
    fault_after_acknowledgment(); receive_reentry(); bounded_flood(); full_valid_vectors();
    printf("{\"cases\":%u,\"assertions\":%lu,\"sreg_patterns\":256,\"fault_byte_cases\":%u,"
           "\"ring_wrap_cases\":%u,\"race_cases\":%u,\"queue_bytes\":%zu,\"event_bytes\":%zu,"
           "\"target_executed\":false}\n", cases, checks, fault_cases, wrap_cases,
           race_cases, sizeof(rx), sizeof(hms_avr_uart_event));
    return 0;
}
#else
/* Cross-link-only harness: deliberately no vector registration, UART setup,
 * runtime loop or physical qualification. This target binary is never run. */
hms_avr_uart hms_avr_uart_probe_queue;
hms_frame_parser hms_avr_uart_probe_parser;
hms_avr_uart_event hms_avr_uart_probe_event;
hms_frame_result hms_avr_uart_probe_frame;
volatile uint8_t hms_avr_uart_probe_result;
_Static_assert(sizeof(hms_avr_uart) == 41, "Reviewed fixed queue storage");
_Static_assert(sizeof(hms_avr_uart_event) == 4, "Reviewed event ABI");
int main(void) {
    hms_avr_uart_init(&hms_avr_uart_probe_queue);
    hms_frame_reset(&hms_avr_uart_probe_parser);
    hms_avr_uart_receive(&hms_avr_uart_probe_queue);
    hms_avr_uart_discontinuity(&hms_avr_uart_probe_queue);
    hms_avr_uart_probe_result = (uint8_t)hms_avr_uart_frame_step(&hms_avr_uart_probe_queue,
        &hms_avr_uart_probe_parser, &hms_avr_uart_probe_event, &hms_avr_uart_probe_frame);
    return 0;
}
#endif
