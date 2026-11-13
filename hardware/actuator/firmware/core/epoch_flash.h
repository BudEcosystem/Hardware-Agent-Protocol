/* Wear-aware, power-fail-safe persistent boot counter for NOR flash (the BHMS epoch).
 *
 * Layout: two erase sectors used as a ping-pong log. Each record is one flash page
 * (programmed exactly once per erase): magic, epoch, ~epoch, CRC-32 of the first 12 bytes,
 * the rest left erased (0xFF). A boot appends the next page of the active sector; when it
 * is full the *other* sector is erased and the record goes to its page 0. The newest valid
 * record anywhere wins, so a torn write or an interrupted erase can only lose the epoch that
 * was being written (which was never advertised, because store returns success only after
 * the page reads back), never an older one.
 *
 * Wear: with 4 KiB sectors and 256-byte pages a sector holds 16 records, so each sector is
 * erased once per 32 boots: 100 000 erase cycles give over 3 million boots.
 *
 * The flash itself is behind `epoch_flash_ops`, so the scheme is tested natively with power
 * failure injected at every program/erase step. Thread-safety: single owner; the ops may
 * block (an erase takes tens of ms), so call from start-up before bhms_init. */
#ifndef ARM_EPOCH_FLASH_H
#define ARM_EPOCH_FLASH_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EPOCH_SECTOR_BYTES 4096u
#define EPOCH_PAGE_BYTES 256u
#define EPOCH_PAGES_PER_SECTOR (EPOCH_SECTOR_BYTES / EPOCH_PAGE_BYTES)
#define EPOCH_MAGIC 0x31485045u /* "EPH1" little endian */

typedef struct {
    void *ctx;
    /* Read n bytes at the given byte offset inside the two-sector region (0 .. 8191). */
    void (*read)(void *ctx, uint32_t offset, uint8_t *out, size_t n);
    /* Erase sector 0 or 1 (all bytes become 0xFF). Returns 0 on success. */
    int (*erase_sector)(void *ctx, unsigned sector);
    /* Program exactly one page (EPOCH_PAGE_BYTES) at page index 0..15 of a sector.
     * Returns 0 on success. */
    int (*program_page)(void *ctx, unsigned sector, unsigned page, const uint8_t *data);
} epoch_flash_ops;

typedef struct {
    const epoch_flash_ops *ops;
} epoch_flash;

void epoch_flash_init(epoch_flash *ef, const epoch_flash_ops *ops);
/* Newest stored epoch; 0 when the region is erased or holds no valid record. */
uint32_t epoch_flash_latest(const epoch_flash *ef);
/* bhms_hal.epoch_load / epoch_store shapes: 0 on success. store requires epoch to be
 * greater than the latest stored value and verifies the page by reading it back. */
int epoch_flash_load(void *ctx, uint32_t *epoch);
int epoch_flash_store(void *ctx, uint32_t epoch);

uint32_t epoch_crc32(const uint8_t *p, size_t n);

#ifdef __cplusplus
}
#endif
#endif
