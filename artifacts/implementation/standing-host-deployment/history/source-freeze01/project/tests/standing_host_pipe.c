#define _POSIX_C_SOURCE 200809L
#include "standing_fixture.h"
#include "../protocol/endpoint/link.h"
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Source-only synthetic pipe bridge. The reviewed runner owns process limits,
 * private duplex descriptors, lifetime, and deterministic command ordering.
 * There is no executable/path/device/network selection and no fork, open,
 * physical output, or wall-clock translation here. stdin/stdout carry only
 * original serial frames through the actual endpoint parser/link/core.
 * The private control FD is deliberately outside the production wire protocol.
 * A control acknowledgment is sent after its bounded action completes. */
static hms_endpoint endpoint;
static hms_standing standing;
static hms_st_arena arena;
static hms_ep_config finite_config;
static hms_st_config standing_config;
static hms_endpoint_link link_state;

static uint32_t read32(const uint8_t *p) { return hms_st_fixture_read32(p); }
static uint64_t read64(const uint8_t *p) { return hms_st_fixture_read64(p); }
static void put32(uint8_t *p, uint32_t value) { hms_st_fixture_write32(p, value); }
static void put64(uint8_t *p, uint64_t value) { hms_st_fixture_write64(p, value); }
static uint16_t flags(void) {
    return (uint16_t)(((uint16_t)arena.driver[FX_FLAGS] << 8) | arena.driver[FX_FLAGS + 1]);
}
static void put_flags(uint16_t value) {
    arena.driver[FX_FLAGS] = (uint8_t)(value >> 8);
    arena.driver[FX_FLAGS + 1] = (uint8_t)value;
}
static int write_all(int fd, const uint8_t *bytes, size_t length) {
    unsigned interrupted = 0;
    while (length != 0u) {
        struct pollfd descriptor;
        ssize_t written;
        int ready;
        descriptor.fd = fd; descriptor.events = POLLOUT; descriptor.revents = 0;
        ready = poll(&descriptor, 1, 1000);
        if (ready < 0 && errno == EINTR && interrupted++ < 16u) continue;
        if (ready <= 0 || (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0 ||
                (descriptor.revents & POLLOUT) == 0) return 0;
        written = write(fd, bytes, length);
        if (written < 0 && errno == EINTR && interrupted++ < 16u) continue;
        if (written <= 0) return 0;
        bytes += (size_t)written; length -= (size_t)written;
    }
    return 1;
}
static int flush_wire(void) {
    /* Maximum serial wire frame = 2 * (20 + 192 + 2) + 2 = 430.
     * One fixed buffer merely batches original link output on the native host;
     * it is neither endpoint storage nor an alternate framing implementation. */
    uint8_t wire[430], byte;
    size_t length = 0;
    while (hms_endpoint_link_next(&link_state, &byte) != 0u) {
        if (length == sizeof(wire)) return 0;
        wire[length++] = byte;
    }
    return length == 0u || write_all(STDOUT_FILENO, wire, length);
}
static int initialize(uint64_t boot, uint8_t reconciliation) {
    hms_st_fixture_init(&arena, &finite_config, &standing_config);
    if (reconciliation != 0u) put_flags((uint16_t)(flags() | HMS_EP_RECONCILE));
    hms_endpoint_link_init(&link_state);
    return hms_endpoint_init(&endpoint, &finite_config, boot, 0, flags()) != 0u &&
           hms_standing_attach(&standing, &endpoint, &standing_config, &arena) != 0u;
}
static void tick_one(uint64_t at) {
    put64(arena.driver + FX_CLOCK, at);
    hms_endpoint_poll(&endpoint, at, flags());
    hms_endpoint_link_check_deadline(&link_state, read64(arena.driver + FX_CLOCK));
}
static int snapshot(uint64_t selector, uint64_t *value) {
    switch (selector) {
        case 0: *value = read32(arena.driver + FX_DISPATCHES); break;
        case 1: *value = read32(arena.driver + FX_LOSSES); break;
        case 2: *value = arena.driver[FX_OUTPUT]; break;
        case 3: *value = read32(arena.driver + FX_SEQUENCE); break;
        case 4: *value = read32(arena.driver + FX_SEQUENCE + 4); break;
        case 5: *value = standing.bytes[ST_LIFE]; break;
        case 6: *value = (uint16_t)(((uint16_t)standing.bytes[ST_FLAGS] << 8) | standing.bytes[ST_FLAGS + 1]); break;
        case 7: *value = read64(arena.driver + FX_CLOCK); break;
        case 8: *value = endpoint.control_generation; break;
        case 9: *value = read32(standing.bytes + ST_HIGH); break;
        case 10: *value = read32(standing.bytes + ST_ACT); break;
        case 11: *value = read32(standing.bytes + ST_ACK); break;
        case 12: *value = read32(standing.bytes + ST_REV); break;
        case 13: *value = read32(standing.bytes + ST_MUT); break;
        case 14: *value = standing.bytes[ST_OWNED]; break;
        case 15: *value = standing.bytes[ST_QUIET]; break;
        case 16: *value = flags(); break;
        case 17: *value = read32(arena.driver + FX_STEP_ADVANCE); break;
        case 18: *value = read32(arena.driver + FX_GUARD_ADVANCE); break;
        case 19: *value = read32(arena.driver + FX_EPOCH); break;
        case 20: *value = read32(arena.driver + FX_EPOCH + 4); break;
        case 21: *value = endpoint.boot_epoch; break;
        case 22: *value = endpoint.response_sequence; break;
        case 23: *value = standing.bytes[ST_LOSS_COMMAND]; break;
        case 24: *value = read32(standing.bytes + ST_ACCOUNT); break;
        case 25: *value = standing.bytes[ST_COUNT]; break;
        case 26: *value = read32(arena.driver + FX_DEMAND); break;
        case 27: *value = read32(arena.driver + FX_FEEDBACK); break;
        default: return 0;
    }
    return 1;
}
static int control(int fd, uint8_t command[9]) {
    uint8_t kind = command[0];
    uint64_t argument = read64(command + 1), reply = argument;
    uint32_t channel;
    int accepted = 1;
    switch (kind) {
        case 1: tick_one(argument); break;
        case 2:
            if (argument > UINT64_MAX - 3u) { accepted = 0; break; }
            tick_one(argument); tick_one(argument + 1u); tick_one(argument + 2u); break;
        case 3:
            if (argument > UINT32_MAX) accepted = 0;
            else put32(arena.driver + FX_DEMAND, (uint32_t)argument);
            break;
        case 4:
            if (argument > UINT8_MAX) accepted = 0;
            else arena.driver[FX_INJECT] = (uint8_t)argument;
            break;
        case 5: accepted = snapshot(argument, &reply); break;
        case 6:
            channel = (uint32_t)(argument >> 32);
            if (channel > 1u || (uint32_t)argument == 0u) accepted = 0;
            else put32(arena.driver + FX_EPOCH + channel * 4u, (uint32_t)argument);
            break;
        case 7:
            if (argument > 127u || (argument & (HMS_EP_PHYSICAL_COMMISSIONED | HMS_EP_STOP_COMMISSIONED)) != 0u) accepted = 0;
            else put_flags((uint16_t)argument);
            break;
        case 8:
            if (argument > UINT32_MAX) accepted = 0;
            else put32(arena.driver + FX_FEEDBACK, (uint32_t)argument);
            break;
        case 9:
            if (argument > 1u) accepted = 0;
            else arena.driver[FX_DENY] = (uint8_t)argument;
            break;
        case 10:
            if (argument > UINT32_MAX) accepted = 0;
            else put32(arena.driver + FX_STEP_ADVANCE, (uint32_t)argument);
            break;
        case 11:
            if (argument > UINT32_MAX) accepted = 0;
            else put32(arena.driver + FX_GUARD_ADVANCE, (uint32_t)argument);
            break;
        case 12:
            if (argument > 3u) accepted = 0;
            else arena.driver[FX_BOUNDARY_DRIFT] = (uint8_t)argument;
            break;
        case 13:
            if (argument > 2u) accepted = 0;
            else arena.driver[FX_WITNESS_TIME] = (uint8_t)argument;
            break;
        case 14:
            channel = (uint32_t)(argument >> 32);
            if (channel > 1u) accepted = 0;
            else put32(arena.driver + FX_SEQUENCE + channel * 4u, (uint32_t)argument);
            break;
        case 15:
            if (argument == 0u || argument <= endpoint.boot_epoch || link_state.receive_partial != 0u ||
                    link_state.transmit_phase != 0u) accepted = 0;
            else accepted = initialize(argument, 1);
            break;
        default: accepted = 0; break;
    }
    command[0] = accepted != 0 ? kind : 255u;
    put64(command + 1, accepted != 0 ? reply : 1u);
    return write_all(fd, command, 9);
}
static int control_descriptor(const char *text, int *result) {
    unsigned long value;
    const char *p;
    char *end;
    if (text == NULL || *text == '\0') return 0;
    for (p = text; *p != '\0'; ++p) if (*p < '0' || *p > '9') return 0;
    errno = 0; value = strtoul(text, &end, 10);
    if (errno != 0 || *end != '\0' || value < 3u || value > INT_MAX) return 0;
    *result = (int)value; return 1;
}
int main(int argc, char **argv) {
    int control_fd;
    uint8_t command[9], command_length = 0, input[256];
    if (argc != 3 || strcmp(argv[1], "--test-control-fd") != 0 ||
            control_descriptor(argv[2], &control_fd) == 0) return 2;
    if (initialize(1, 0) == 0) return 3;
    for (;;) {
        struct pollfd descriptors[2];
        int ready;
        descriptors[0].fd = STDIN_FILENO; descriptors[0].events = POLLIN; descriptors[0].revents = 0;
        descriptors[1].fd = control_fd; descriptors[1].events = POLLIN; descriptors[1].revents = 0;
        ready = poll(descriptors, 2, 1000);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) return 3;
        if (ready == 0) continue; /* No automatic endpoint work or clock advance. */
        if ((descriptors[0].revents & (POLLERR | POLLNVAL)) != 0 ||
                (descriptors[1].revents & (POLLERR | POLLNVAL)) != 0) return 3;
        /* Process already available wire bytes before controls. Cross-FD
         * semantic ordering still requires the runner to await wire replies. */
        if ((descriptors[0].revents & (POLLIN | POLLHUP)) != 0) {
            ssize_t n = read(STDIN_FILENO, input, sizeof(input));
            size_t index;
            if (n == 0) return 0;
            if (n < 0) { if (errno == EINTR) continue; return 3; }
            for (index = 0; index < (size_t)n; ++index) {
                hms_endpoint_link_feed(&link_state, &endpoint, input[index],
                                       read64(arena.driver + FX_CLOCK), flags());
                if (flush_wire() == 0) return 3;
            }
        }
        if ((descriptors[1].revents & (POLLIN | POLLHUP)) != 0) {
            ssize_t n = read(control_fd, command + command_length, (size_t)(9u - command_length));
            if (n == 0) return 0;
            if (n < 0) { if (errno == EINTR) continue; return 3; }
            command_length = (uint8_t)(command_length + (uint8_t)n);
            if (command_length == 9u) {
                if (control(control_fd, command) == 0) return 3;
                command_length = 0;
            }
        }
    }
}
