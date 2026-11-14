/* simavr runner: executes an AVR firmware ELF with its UART0 on stdin/stdout, so
 * the pty-based host harness (tests/host/test_e2e.py) drives real firmware.
 *
 *   runner --mcu atmega328p --freq 16000000 [--adc0-mv N] [--led-pin 5]
 *          [--eeprom FILE] firmware.elf
 *
 * - UART0 TX bytes go to stdout; stdin bytes feed UART0 RX (with simavr's own
 *   XOFF/XON flow control honoured, baud timing emulated by simavr).
 * - PORTB `--led-pin` transitions are reported on stderr as "LED 0|1". Nothing
 *   else is written there while the firmware runs: simavr's own echo of the
 *   UART output is switched off (see main).
 * - The run is paced to wall-clock time so firmware millis() matches the
 *   harness's timeouts.
 * - EEPROM is loaded from / saved to FILE (every 200 ms of wall time when it
 *   changed, and on SIGTERM), making the boot counter persist across runs.
 * Build: gcc runner.c -o runner $(pkg-config --cflags --libs simavr) -lelf */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

#include "avr_adc.h"
#include "avr_eeprom.h"
#include "avr_ioport.h"
#include "avr_uart.h"
#include "sim_avr.h"
#include "sim_elf.h"

#define PENDING_CAP 8192
#define EEPROM_IMAGE 64

static volatile sig_atomic_t g_stop;
static uint8_t g_pending[PENDING_CAP];
static size_t g_pend_head, g_pend_len;
static int g_xoff;
static int g_led_last;

static void on_term(int sig) {
    (void)sig;
    g_stop = 1;
}

static void uart_out(struct avr_irq_t *irq, uint32_t value, void *param) {
    uint8_t b = (uint8_t)value;
    (void)irq;
    (void)param;
    while (write(1, &b, 1) < 0 && errno == EINTR) {
    }
}

static void xon(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq;
    (void)value;
    (void)param;
    g_xoff = 0;
}

static void xoff(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq;
    (void)value;
    (void)param;
    g_xoff = 1;
}

static void led_changed(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq;
    (void)param;
    if ((int)value != g_led_last) {
        g_led_last = (int)value;
        fprintf(stderr, "LED %d\n", g_led_last);
        fflush(stderr);
    }
}

static uint64_t wall_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* The simavr 1.6 EEPROM ioctls copy and return correctly but report -1 even on
 * success, so success is judged by the effect (a returned pointer), not the
 * return code. */
static void load_eeprom(avr_t *avr, const char *path) {
    uint8_t buf[EEPROM_IMAGE];
    avr_eeprom_desc_t d;
    FILE *f;
    size_t n;
    if (path == NULL || (f = fopen(path, "rb")) == NULL) return;
    n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    memset(&d, 0, sizeof d);
    d.ee = buf;
    d.offset = 0;
    d.size = (uint32_t)n;
    (void)avr_ioctl(avr, AVR_IOCTL_EEPROM_SET, &d);
}

static void save_eeprom(avr_t *avr, const char *path) {
    avr_eeprom_desc_t d;
    FILE *f;
    if (path == NULL) return;
    memset(&d, 0, sizeof d);
    (void)avr_ioctl(avr, AVR_IOCTL_EEPROM_GET, &d); /* d.ee now points at the array */
    if (d.ee == NULL) {
        fprintf(stderr, "runner: eeprom unavailable\n");
        return;
    }
    if ((f = fopen(path, "wb")) == NULL) return;
    fwrite(d.ee, 1, EEPROM_IMAGE, f); /* the library uses only the first bytes */
    fclose(f);
}

int main(int argc, char **argv) {
    const char *mcu = "atmega328p", *eeprom = NULL, *elf = NULL;
    unsigned freq = 16000000u;
    int adc0_mv = -1, led_pin = 5, i;
    elf_firmware_t fw;
    avr_t *avr;
    uint64_t t0, next_poll = 0, last_save = 0;

    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--mcu") && i + 1 < argc) mcu = argv[++i];
        else if (!strcmp(argv[i], "--freq") && i + 1 < argc) freq = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--adc0-mv") && i + 1 < argc) adc0_mv = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--led-pin") && i + 1 < argc) led_pin = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--eeprom") && i + 1 < argc) eeprom = argv[++i];
        else elf = argv[i];
    }
    if (elf == NULL) {
        fprintf(stderr, "usage: runner [--mcu M] [--freq HZ] [--adc0-mv N] [--led-pin N] [--eeprom F] fw.elf\n");
        return 2;
    }
    memset(&fw, 0, sizeof fw);
    if (elf_read_firmware(elf, &fw) != 0) {
        fprintf(stderr, "cannot read %s\n", elf);
        return 2;
    }
    avr = avr_make_mcu_by_name(mcu);
    if (avr == NULL) {
        fprintf(stderr, "unknown mcu %s\n", mcu);
        return 2;
    }
    avr_init(avr);
    avr_load_firmware(avr, &fw);
    avr->frequency = freq;
    avr->vcc = avr->avcc = avr->aref = 5000;
    load_eeprom(avr, eeprom);

    /* simavr echoes what the firmware transmits as a text line on stderr (AVR_UART_FLAG_STDIO, on by default): at every
     * 0x0A in the stream, or after 256 bytes, it prints "ESC[32m<bytes>\n" and leaves the colour reset "ESC[0m" to start
     * the next line. Here the UART carries binary frames and stderr is the effect report, so that echo put frame bytes
     * into it and turned the next "LED 1" into "ESC[0mLED 1" whenever a frame held 0x0A (about 1 HELLO in 40). */
    {
        uint32_t uart_flags = 0;
        (void)avr_ioctl(avr, AVR_IOCTL_UART_GET_FLAGS('0'), &uart_flags);
        uart_flags &= ~(uint32_t)AVR_UART_FLAG_STDIO;
        (void)avr_ioctl(avr, AVR_IOCTL_UART_SET_FLAGS('0'), &uart_flags);
    }
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUTPUT), uart_out, NULL);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUT_XOFF), xoff, NULL);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUT_XON), xon, NULL);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ('B'), led_pin), led_changed, NULL);
    if (adc0_mv >= 0)
        avr_raise_irq(avr_io_getirq(avr, AVR_IOCTL_ADC_GETIRQ, ADC_IRQ_ADC0), (uint32_t)adc0_mv);

    signal(SIGTERM, on_term);
    signal(SIGINT, on_term);
    fcntl(0, F_SETFL, fcntl(0, F_GETFL, 0) | O_NONBLOCK);
    t0 = wall_ns();
    avr_irq_t *rx = avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_INPUT);

    while (!g_stop) {
        int state = cpu_Running;
        uint64_t now, sim_ns;
        unsigned k;
        for (k = 0; k < 4000u && state != cpu_Done && state != cpu_Crashed; ++k)
            state = avr_run(avr);
        now = wall_ns() - t0;
        sim_ns = avr->cycle * 1000000000ull / avr->frequency;
        if (state == cpu_Done || state == cpu_Crashed) break;
        if (sim_ns > now + 200000ull) { /* ahead of wall time: pace to real time */
            uint64_t gap = sim_ns - now > 2000000ull ? 2000000ull : sim_ns - now;
            /* Wake early when input arrives. */
            fd_set rf;
            struct timeval tv = {0, (suseconds_t)(gap / 1000)};
            FD_ZERO(&rf);
            FD_SET(0, &rf);
            select(1, &rf, NULL, NULL, &tv);
        }
        if (now >= next_poll) {
            uint8_t tmp[256];
            ssize_t n = read(0, tmp, sizeof tmp);
            next_poll = now + 200000ull; /* poll stdin every 200 us of wall time */
            if (n > 0) {
                size_t k;
                for (k = 0; k < (size_t)n && g_pend_len < PENDING_CAP; ++k)
                    g_pending[(g_pend_head + g_pend_len++) % PENDING_CAP] = tmp[k];
            } else if (n == 0) {
                break; /* harness closed the pty */
            }
            while (g_pend_len > 0 && !g_xoff) {
                avr_raise_irq(rx, g_pending[g_pend_head]);
                g_pend_head = (g_pend_head + 1) % PENDING_CAP;
                --g_pend_len;
            }
        }
        if (now - last_save > 200000000ull) {
            last_save = now;
            save_eeprom(avr, eeprom);
        }
    }
    save_eeprom(avr, eeprom);
    return 0;
}
