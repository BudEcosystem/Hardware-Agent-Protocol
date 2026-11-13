/* Flash backend of the epoch store (core/epoch_flash.c) for the RP2040: the last two 4 KiB
 * sectors of the QSPI flash. Erase and program run through flash_safe_execute (interrupts off,
 * XIP paused); they only happen at boot, before the servo rail or any operation exists. */
#include <string.h>

#include "board.h"
#include "epoch_flash.h"
#include "hardware/flash.h"
#include "hardware/watchdog.h"
#include "pico/flash.h"
#include "pico/stdlib.h"

/* Two regions at the end of the flash; the ops context is the region's byte offset. */
static uint32_t g_epoch_offset = PICO_FLASH_SIZE_BYTES - EPOCH_REGION_BYTES;
static uint32_t g_cal_offset = PICO_FLASH_SIZE_BYTES - EPOCH_REGION_BYTES - CAL_REGION_BYTES;

typedef struct {
    uint32_t offset;
    const uint8_t *data;
    int op; /* 0 erase, 1 program */
} flash_job;

static void __not_in_flash_func(do_job)(void *p) {
    flash_job *j = (flash_job *)p;
    if (j->op == 0) flash_range_erase(j->offset, FLASH_SECTOR_SIZE);
    else flash_range_program(j->offset, j->data, FLASH_PAGE_SIZE);
}

static void f_read(void *c, uint32_t off, uint8_t *out, size_t n) {
    memcpy(out, (const void *)(XIP_BASE + *(const uint32_t *)c + off), n);
}

static int f_erase(void *c, unsigned sector) {
    flash_job j = {*(const uint32_t *)c + sector * FLASH_SECTOR_SIZE, 0, 0};
    return flash_safe_execute(do_job, &j, 1000) == PICO_OK ? 0 : -1;
}

static int f_program(void *c, unsigned sector, unsigned page, const uint8_t *data) {
    flash_job j = {*(const uint32_t *)c + sector * FLASH_SECTOR_SIZE + page * FLASH_PAGE_SIZE, data, 1};
    watchdog_update();
    return flash_safe_execute(do_job, &j, 1000) == PICO_OK ? 0 : -1;
}

#include "hw_rp2040.h"
static const epoch_flash_ops g_epoch_ops = {&g_epoch_offset, f_read, f_erase, f_program, hw_wdt_slow_begin, hw_wdt_slow_end};
static const epoch_flash_ops g_cal_ops = {&g_cal_offset, f_read, f_erase, f_program, hw_wdt_slow_begin, hw_wdt_slow_end};
const epoch_flash_ops *flash_epoch_ops(void) { return &g_epoch_ops; }
const epoch_flash_ops *flash_cal_ops(void) { return &g_cal_ops; }

_Static_assert(EPOCH_SECTOR_BYTES == FLASH_SECTOR_SIZE, "epoch sectors are flash erase sectors");
_Static_assert(EPOCH_PAGE_BYTES == FLASH_PAGE_SIZE, "epoch records are flash pages");
