#define _POSIX_C_SOURCE 200809L
#include "../protocol/endpoint/scenario_fixture.h"
#include "../protocol/endpoint/link.h"
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* Synthetic three-scenario process harness only. A connected duplex socket may
 * be inherited as both stdin and stdout; no endpoint lifetime is tied to a
 * particular Runtime object. Socket ownership is an external test obligation. Binary stdin/stdout are the original serial
 * frame stream. The optional inherited duplex test FD is never production
 * wire authority. Its acknowledged 9-byte commands establish deterministic
 * test ordering. No device, UART, NVM, physical output or OS account is opened. */
static hms_endpoint endpoint;
static hms_endpoint_link link_state;
static hms_scenario_fixture fixture;
static hms_ep_config config;
static struct timespec clock_origin;
static uint8_t clock_is_deterministic;
static uint64_t *clock_value;
static uint16_t *clock_flags;

static uint64_t get64(const uint8_t *p) {
    uint8_t i; uint64_t v = 0;
    for (i = 0; i < 8u; ++i) v = (v << 8) | p[i];
    return v;
}
static void put64(uint8_t *p, uint64_t v) {
    uint8_t i;
    for (i = 0; i < 8u; ++i) { p[7u-i] = (uint8_t)v; v >>= 8; }
}
static int write_all(int fd, const uint8_t *p, size_t n) {
    while (n != 0u) {
        ssize_t written = write(fd, p, n);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return 0;
        p += (size_t)written; n -= (size_t)written;
    }
    return 1;
}
static int flush_wire(void) {
    uint8_t byte;
    while (hms_endpoint_link_next(&link_state, &byte) != 0u)
        if (write_all(STDOUT_FILENO, &byte, 1) == 0) return 0;
    return 1;
}
static int unsigned_arg(const char *text, uint64_t *value) {
    char *end; unsigned long long parsed;
    if (*text < '0' || *text > '9') return 0;
    errno = 0; parsed = strtoull(text, &end, 10);
    if (errno != 0 || *end != '\0') return 0;
    *value = (uint64_t)parsed; return 1;
}
static uint64_t monotonic_tick(const struct timespec *origin, uint16_t *flags) {
    struct timespec now;
    uint64_t seconds, result;
    long nanos;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 || now.tv_sec < origin->tv_sec) {
        *flags = (uint16_t)(*flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED);
        return endpoint.now_tick;
    }
    seconds = (uint64_t)(now.tv_sec - origin->tv_sec);
    nanos = now.tv_nsec - origin->tv_nsec;
    if (nanos < 0) { if (seconds == 0u) return endpoint.now_tick; --seconds; nanos += 1000000000L; }
    if (seconds > (UINT64_MAX - 1000u) / 1000u) {
        *flags = (uint16_t)(*flags & (uint16_t)~HMS_EP_CLOCK_QUALIFIED); return endpoint.now_tick;
    }
    result = 1000u + seconds * 1000u + (uint64_t)nanos / 1000000u;
    return result;
}
static uint8_t harness_clock(void *user, uint64_t *tick, uint16_t *flags) {
    hms_scenario_fixture *f = user;
    if (clock_is_deterministic == 0u) *clock_value = monotonic_tick(&clock_origin, clock_flags);
    else if (f->clock_tick > *clock_value) *clock_value = f->clock_tick;
    *tick = *clock_value; *flags = *clock_flags;
    f->clock_tick = *tick; f->platform_flags = *flags;
    return 1;
}
static int control(int fd, uint8_t *command, uint64_t *now, uint16_t *flags) {
    uint8_t kind = command[0], accepted = 1;
    uint64_t argument = get64(command + 1), reply = argument;
    switch (kind) {
        case 1:
            *now = argument; fixture.clock_tick = *now; fixture.platform_flags = *flags;
            hms_endpoint_poll(&endpoint, *now, *flags); hms_endpoint_link_check_deadline(&link_state,*now); break;
        case 2:
            if (argument == 0u || argument <= endpoint.boot_epoch) { accepted = 0; break; }
            *now = 1000; *flags = HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY | HMS_EP_RECONCILE;
            fixture.active = fixture.pending_quiescence = 0;
            fixture.clock_tick = *now; fixture.platform_flags = *flags;
            hms_endpoint_link_init(&link_state);
            if (hms_endpoint_init(&endpoint, &config, argument, *now, *flags) == 0u) accepted = 0;
            break;
        case 3:
            if (argument > 127u || (argument & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_STOP_COMMISSIONED)) != 0u) { accepted = 0; break; }
            *flags = (uint16_t)argument; fixture.clock_tick = *now; fixture.platform_flags = *flags;
            hms_endpoint_poll(&endpoint, *now, *flags); break;
        case 4: if (argument != 0u) accepted = 0; else reply = fixture.dispatches; break;
        case 5: if (argument != 0u) accepted = 0; else reply = fixture.effects; break;
        case 6: if (argument > HMS_SCENARIO_LATE_CALLBACK || (argument == HMS_SCENARIO_LATE_CALLBACK && clock_is_deterministic == 0u)) accepted = 0; else fixture.mode = (uint8_t)argument; break;
        case 7:
            if (argument > 1000000u || endpoint.receipt.execution != HMS_EP_EMPTY) accepted = 0;
            else fixture.values[2] = (uint32_t)argument;
            break;
        default: accepted = 0; break;
    }
    command[0] = accepted != 0u ? kind : 255u;
    put64(command + 1, accepted != 0u ? reply : 1u);
    return write_all(fd, command, 9);
}
int main(int argc, char **argv) {
    uint64_t boot = 42, now = 1000, argument;
    uint16_t flags = HMS_EP_BOOT_QUALIFIED | HMS_EP_CLOCK_QUALIFIED | HMS_EP_SIMULATOR_ONLY;
    uint8_t deterministic = 0, control_bytes[9], control_length = 0, input[256];
    int control_fd = -1, i;
    struct timespec origin;
    hms_scenario_fixture_init(&fixture, &config);
    for (i = 1; i < argc; ++i) {
        if (i + 1 >= argc) return 2;
        if (strcmp(argv[i], "--test-control-fd") == 0) {
            if (unsigned_arg(argv[++i], &argument) == 0 || argument > INT_MAX) return 2;
            control_fd = (int)argument; deterministic = 1;
        } else if (strcmp(argv[i], "--boot") == 0) {
            if (unsigned_arg(argv[++i], &boot) == 0 || boot == 0u) return 2;
        } else if (strcmp(argv[i], "--manifest") == 0) {
            if (hms_scenario_fixture_constant(&fixture, HMS_EP_MANIFEST, argv[++i]) == 0u) return 2;
        } else if (strcmp(argv[i], "--firmware") == 0) {
            if (hms_scenario_fixture_constant(&fixture, HMS_EP_FIRMWARE, argv[++i]) == 0u) return 2;
        } else if (strcmp(argv[i], "--incarnation") == 0) {
            if (hms_scenario_fixture_constant(&fixture, HMS_EP_INCARNATION, argv[++i]) == 0u) return 2;
        } else return 2;
    }
    if (clock_gettime(CLOCK_MONOTONIC, &origin) != 0) return 3;
    clock_origin = origin; clock_is_deterministic = deterministic;
    clock_value = &now; clock_flags = &flags; fixture.clock_snapshot = harness_clock;
    hms_endpoint_link_init(&link_state);
    if (hms_endpoint_init(&endpoint, &config, boot, now, flags) == 0u) return 3;
    for (;;) {
        struct pollfd descriptors[2];
        int ready;
        if (deterministic == 0u) { now = monotonic_tick(&origin, &flags); fixture.clock_tick = now; fixture.platform_flags = flags; hms_endpoint_poll(&endpoint, now, flags); hms_endpoint_link_check_deadline(&link_state,now); }
        descriptors[0].fd = STDIN_FILENO; descriptors[0].events = POLLIN; descriptors[0].revents = 0;
        descriptors[1].fd = control_fd; descriptors[1].events = POLLIN; descriptors[1].revents = 0;
        ready = poll(descriptors, 2, deterministic != 0u ? -1 : 2);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) return 3;
        if ((descriptors[1].revents & (POLLIN | POLLHUP)) != 0) {
            ssize_t n = read(control_fd, control_bytes + control_length, (size_t)(9u - control_length));
            if (n > 0) {
                control_length = (uint8_t)(control_length + (uint8_t)n);
                if (control_length == 9u) {
                    if (control(control_fd, control_bytes, &now, &flags) == 0) return 3;
                    control_length = 0;
                }
            } else if (n == 0) control_fd = -1;
            else if (errno != EINTR) return 3;
        }
        if ((descriptors[0].revents & (POLLIN | POLLHUP)) != 0) {
            ssize_t n = read(STDIN_FILENO, input, sizeof(input));
            size_t index;
            if (n == 0) return 0;
            if (n < 0) { if (errno == EINTR) continue; return 3; }
            if (deterministic == 0u) now = monotonic_tick(&origin, &flags);
            fixture.clock_tick = now; fixture.platform_flags = flags;
            for (index = 0; index < (size_t)n; ++index) {
                hms_endpoint_link_feed(&link_state, &endpoint, input[index], now, flags);
                if (flush_wire() == 0) return 3;
            }
        }
    }
}
