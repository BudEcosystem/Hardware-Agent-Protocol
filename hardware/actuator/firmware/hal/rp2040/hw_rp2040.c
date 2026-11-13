#include "hw_rp2040.h"

#include <string.h>

#include "board.h"
#include "epoch_flash.h"
#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "cal_store.h"
#include "pico/stdlib.h"
#include "pico/stdio/driver.h"
#include "pico/stdio_usb.h"
#include "power.h"

/* ---- E-stop latch ---------------------------------------------------------------------
 * The rising edge of contact B clears SERVO_EN from the IRQ (INTERFACE.md section 4: within
 * 1 ms, the hardware path has already cut the rail) and sets one latch per consumer, so the
 * arm logic and the BHMS endpoint each see the edge exactly once. */
static volatile uint8_t g_edge_arm, g_edge_bhms;

static void __not_in_flash_func(estop_irq)(uint gpio, uint32_t events) {
    (void)events;
    if (gpio != PIN_ESTOP_SENSE) return;
    gpio_put(PIN_SERVO_EN, 0);
    g_edge_arm = 1;
    g_edge_bhms = 1;
}

static int take_flag(volatile uint8_t *f) {
    uint32_t s = save_and_disable_interrupts();
    int v = *f;
    *f = 0;
    restore_interrupts(s);
    return v;
}

/* ---- Servo bus ---------------------------------------------------------------------------- */
#define RX_RING 256u
static uint8_t g_rx[RX_RING];
static uint16_t g_rx_head, g_rx_len;

static void pump_rx(void) {
    while (uart_is_readable(uart0)) {
        uint8_t b = (uint8_t)(uart_get_hw(uart0)->dr & 0xFFu);
        if (g_rx_len < RX_RING) g_rx[(g_rx_head + g_rx_len++) % RX_RING] = b;
    }
}

static void bus_flush(void *c) {
    (void)c;
    pump_rx();
    g_rx_head = g_rx_len = 0;
}

/* INTERFACE.md section 3: enable the driver, write, wait for TX-complete (not FIFO empty),
 * release the driver within 5 us. Interrupts are off for the frame (<= 0.6 ms at 1 Mbps) so a USB
 * interrupt cannot delay the release into the servo's reply. The echo is drained as it arrives:
 * a 48-byte frame is longer than the 32-byte RX FIFO. */
#define BUS_WRITE_BUDGET_US 3000u /* a 54-byte frame takes 0.54 ms: 3 ms is a stuck UART */

static void __not_in_flash_func(bus_write)(void *c, const uint8_t *buf, size_t n) {
    uint32_t irq = save_and_disable_interrupts();
    uint32_t t0 = time_us_32();
    size_t i;
    (void)c;
    gpio_put(PIN_BUS_TXEN_N, 0);
    for (i = 0; i < n; ++i) {
        /* Every wait is bounded by one budget: with interrupts off nothing may spin forever. */
        while (!uart_is_writable(uart0)) {
            pump_rx();
            if ((uint32_t)(time_us_32() - t0) > BUS_WRITE_BUDGET_US) goto release;
        }
        uart_get_hw(uart0)->dr = buf[i];
        pump_rx();
    }
    while ((uart_get_hw(uart0)->fr & UART_UARTFR_BUSY_BITS) != 0) {
        pump_rx();
        if ((uint32_t)(time_us_32() - t0) > BUS_WRITE_BUDGET_US) break;
    }
release:
    gpio_put(PIN_BUS_TXEN_N, 1); /* always give the line back: the echo check reports a short frame */
    pump_rx();
    restore_interrupts(irq);
}

static size_t bus_read(void *c, uint8_t *buf, size_t n, uint32_t timeout_us) {
    size_t i;
    (void)c;
    for (i = 0; i < n; ++i) {
        uint32_t t0 = time_us_32();
        for (;;) {
            pump_rx();
            if (g_rx_len > 0) {
                buf[i] = g_rx[g_rx_head];
                g_rx_head = (uint16_t)((g_rx_head + 1u) % RX_RING);
                --g_rx_len;
                break;
            }
            if ((uint32_t)(time_us_32() - t0) > timeout_us) return i;
        }
    }
    return n;
}

/* ---- GPIO, ADC, INA219, LED ----------------------------------------------------------------- */
static uint32_t millis(void *c) { (void)c; return to_ms_since_boot(get_absolute_time()); }
static void servo_en(void *c, int on) { (void)c; gpio_put(PIN_SERVO_EN, on != 0); }
static void tool_en(void *c, int on) { (void)c; gpio_put(PIN_TOOL_EN, on != 0); }
static int estop_sense(void *c) { (void)c; return gpio_get(PIN_ESTOP_SENSE); }
static int estop_edge(void *c) { (void)c; return take_flag(&g_edge_arm); }

static uint16_t adc_read_ch(void *c, uint8_t ch) {
    uint32_t sum = 0;
    unsigned i;
    (void)c;
    if (ch > 3u) return 0;
    adc_select_input(ch);
    for (i = 0; i < 4u; ++i) sum += adc_read();
    return (uint16_t)(sum / 4u);
}

static int ina_reg_write(uint8_t reg, uint16_t v) {
    uint8_t b[3] = {reg, (uint8_t)(v >> 8), (uint8_t)(v & 0xFFu)};
    return i2c_write_timeout_us(i2c0, INA219_ADDR, b, 3, false, 2000) == 3 ? 0 : -1;
}

static int ina_reg_read(uint8_t reg, uint16_t *v) {
    uint8_t b[2];
    if (i2c_write_timeout_us(i2c0, INA219_ADDR, &reg, 1, true, 2000) != 1) return -1;
    if (i2c_read_timeout_us(i2c0, INA219_ADDR, b, 2, false, 2000) != 2) return -1;
    *v = (uint16_t)((b[0] << 8) | b[1]);
    return 0;
}

static int ina_read(void *c, uint16_t *bus_reg, int16_t *current_reg) {
    uint16_t cur;
    (void)c;
    if (ina_reg_read(0x02, bus_reg) != 0 || ina_reg_read(0x04, &cur) != 0) return -1;
    *current_reg = (int16_t)cur;
    return 0;
}

static void led(void *c, uint8_t r, uint8_t g, uint8_t b) {
    (void)c;
    gpio_put(PIN_LED_R, r == 0);
    gpio_put(PIN_LED_G, g == 0);
    gpio_put(PIN_LED_B, b == 0);
}

static int wdt_reset(void *c) { (void)c; return watchdog_caused_reboot(); }

/* ---- Flash: boot counter and calibration (only with the servo rail off) ---------------------- */
extern const epoch_flash_ops *flash_epoch_ops(void);
extern const epoch_flash_ops *flash_cal_ops(void);
static epoch_flash g_epoch;
static cal_store g_cal;

static int rail_on(void) { return gpio_get(PIN_SERVO_EN) != 0; }

static int cal_load(void *c, arm_cal *cal) { (void)c; return cal_store_load(&g_cal, cal); }
static int cal_save(void *c, const arm_cal *cal) {
    (void)c;
    if (rail_on()) return -1; /* flash writes mask the E-stop IRQ */
    return cal_store_save(&g_cal, cal);
}

static const arm_hw g_hw = {0, millis, bus_flush, bus_write, bus_read, servo_en, tool_en,
                            estop_sense, estop_edge, adc_read_ch, ina_read, led,
                            wdt_reset, cal_load, cal_save};

const arm_hw *hw_arm(void) { return &g_hw; }

static void out_pin(uint pin, int level) {
    gpio_init(pin);
    gpio_put(pin, level);
    gpio_set_dir(pin, GPIO_OUT);
}

int hw_init(void) {
    int rc = 0;
    /* Reset-safe levels first: rail off, tool power off, bus driver off, LEDs off. */
    out_pin(PIN_SERVO_EN, 0);
    out_pin(PIN_TOOL_EN, 0);
    out_pin(PIN_BUS_TXEN_N, 1);
    out_pin(PIN_LED_R, 1);
    out_pin(PIN_LED_G, 1);
    out_pin(PIN_LED_B, 1);
    gpio_init(PIN_ESTOP_SENSE);
    gpio_set_dir(PIN_ESTOP_SENSE, GPIO_IN);
    /* Servo bus: UART0 at 1 Mbps, 8N1, FIFO on. */
    uart_init(uart0, BUS_BAUD);
    gpio_set_function(PIN_BUS_TX, GPIO_FUNC_UART);
    gpio_set_function(PIN_BUS_RX, GPIO_FUNC_UART);
    uart_set_format(uart0, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(uart0, true);
    /* ADC. */
    adc_init();
    adc_gpio_init(PIN_ADC_TOOL_ID);
    adc_gpio_init(PIN_ADC_AUX1);
    adc_gpio_init(PIN_ADC_AUX2);
    adc_gpio_init(PIN_ADC_VIN);
    /* INA219: configuration 0x299F, calibration 0x4000 (INTERFACE.md section 6). */
    i2c_init(i2c0, I2C_BAUD);
    gpio_set_function(PIN_I2C_SDA, GPIO_FUNC_I2C);
    gpio_set_function(PIN_I2C_SCL, GPIO_FUNC_I2C);
    if (ina_reg_write(0x00, INA219_CONFIG) != 0 || ina_reg_write(0x05, INA219_CALIBRATION) != 0) rc = -1;
    /* E-stop: a latched edge for a press that happened before the IRQ was armed. */
    if (gpio_get(PIN_ESTOP_SENSE)) {
        g_edge_arm = 1;
        g_edge_bhms = 1;
    }
    irq_set_priority(IO_IRQ_BANK0, 0); /* highest: nothing delays the SERVO_EN clear */
    gpio_set_irq_enabled_with_callback(PIN_ESTOP_SENSE, GPIO_IRQ_EDGE_RISE, true, estop_irq);
    return rc;
}

void hw_halt(void) {
    gpio_put(PIN_SERVO_EN, 0);
    gpio_put(PIN_TOOL_EN, 0);
    for (;;) {
        gpio_put(PIN_LED_R, 0);
        sleep_ms(125);
        gpio_put(PIN_LED_R, 1);
        sleep_ms(125);
    }
}

/* ---- BHMS HAL: USB CDC ---------------------------------------------------------------------- */
static uint8_t g_in[64];
static uint8_t g_in_pos, g_in_len;

static int usb_read(void *c) {
    (void)c;
    if (g_in_pos >= g_in_len) {
        int n = stdio_usb.in_chars((char *)g_in, (int)sizeof g_in);
        if (n <= 0) return -1;
        g_in_pos = 0;
        g_in_len = (uint8_t)n;
    }
    return g_in[g_in_pos++];
}

/* Bounded: PICO_STDIO_USB_STDOUT_TIMEOUT_US (20 ms) caps a stalled host. */
static void usb_write(void *c, const uint8_t *buf, size_t n) {
    (void)c;
    stdio_usb.out_chars((const char *)buf, (int)n);
}

static uint32_t bhms_millis(void *c) { return millis(c); }

/* The pin hook: the level or an unread latched edge (a pulse shorter than one poll is kept). */
static int bhms_stop_pin(void *c) {
    int latched = take_flag(&g_edge_bhms);
    (void)c;
    return latched || gpio_get(PIN_ESTOP_SENSE);
}

/* ---- Flash epoch -------------------------------------------------------------------------- */
void hw_epoch_init(void) {
    epoch_flash_init(&g_epoch, flash_epoch_ops());
    cal_store_init(&g_cal, flash_cal_ops());
}

void hw_watchdog_start(void) { watchdog_enable(WATCHDOG_MS, 1); }
void hw_feed(void) { watchdog_update(); }

static int ep_load(void *c, uint32_t *e) { (void)c; return epoch_flash_load(&g_epoch, e); }
/* Boot-time stores happen with the rail off. A NEW_SESSION store at run time while the rail is on
 * is refused (the IRQ must stay live); the endpoint then does not claim PERSISTENT_EPOCH. */
static int ep_store(void *c, uint32_t e) {
    (void)c;
    if (rail_on()) return -1;
    return epoch_flash_store(&g_epoch, e);
}

static const bhms_hal g_bhms = {0, usb_read, usb_write, bhms_millis, bhms_stop_pin, ep_load, ep_store};
const bhms_hal *hw_bhms(void) { return &g_bhms; }
