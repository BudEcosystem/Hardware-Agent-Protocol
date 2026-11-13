#define _POSIX_C_SOURCE 200809L
#include "bhms_hal_posix.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static int p_read(void *ctx) {
    bhms_posix *p = (bhms_posix *)ctx;
    uint8_t b;
    ssize_t n = read(p->in_fd, &b, 1);
    if (n == 1) return b;
    if (n == 0) _exit(0); /* peer closed: the simulated board is powered off */
    return -1;
}

static void p_write(void *ctx, const uint8_t *buf, size_t n) {
    bhms_posix *p = (bhms_posix *)ctx;
    while (n > 0) {
        ssize_t w = write(p->out_fd, buf, n);
        if (w < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            return;
        }
        buf += (size_t)w;
        n -= (size_t)w;
    }
}

static uint32_t p_millis(void *ctx) {
    struct timespec ts;
    (void)ctx;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)((uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u);
}

static int p_epoch_load(void *ctx, uint32_t *epoch) {
    bhms_posix *p = (bhms_posix *)ctx;
    FILE *f = fopen(p->epoch_path, "rb");
    uint8_t b[4];
    *epoch = 0; /* absent file == erased cell */
    if (f == NULL) return 0;
    if (fread(b, 1, 4, f) == 4)
        *epoch = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) |
                 ((uint32_t)b[3] << 24);
    fclose(f);
    return 0;
}

static int p_epoch_store(void *ctx, uint32_t epoch) {
    bhms_posix *p = (bhms_posix *)ctx;
    FILE *f = fopen(p->epoch_path, "wb");
    uint8_t b[4] = {(uint8_t)epoch, (uint8_t)(epoch >> 8), (uint8_t)(epoch >> 16),
                    (uint8_t)(epoch >> 24)};
    int ok;
    if (f == NULL) return -1;
    ok = fwrite(b, 1, 4, f) == 4 && fflush(f) == 0;
    return (fclose(f) == 0 && ok) ? 0 : -1;
}

void bhms_posix_init(bhms_posix *p, int in_fd, int out_fd, const char *epoch_path) {
    int fl = fcntl(in_fd, F_GETFL, 0);
    p->in_fd = in_fd;
    p->out_fd = out_fd;
    p->epoch_path = epoch_path;
    if (fl >= 0) (void)fcntl(in_fd, F_SETFL, fl | O_NONBLOCK);
    p->hal.ctx = p;
    p->hal.uart_read = p_read;
    p->hal.uart_write = p_write;
    p->hal.millis = p_millis;
    p->hal.stop_pin = NULL;
    p->hal.epoch_load = epoch_path != NULL ? p_epoch_load : NULL;
    p->hal.epoch_store = epoch_path != NULL ? p_epoch_store : NULL;
}

int bhms_posix_wait(bhms_posix *p, int timeout_ms) {
    struct pollfd pf;
    pf.fd = p->in_fd;
    pf.events = POLLIN;
    pf.revents = 0;
    return poll(&pf, 1, timeout_ms) > 0 && (pf.revents & POLLIN) != 0;
}
