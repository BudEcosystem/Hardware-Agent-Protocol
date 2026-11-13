#include "epoch_flash.h"

#include <string.h>

#define REC_BYTES 16u

uint32_t epoch_crc32(const uint8_t *p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    size_t i;
    unsigned b;
    for (i = 0; i < n; ++i) {
        crc ^= p[i];
        for (b = 0; b < 8u; ++b) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Returns 1 and the epoch when the page holds a valid record. */
static int read_record(const epoch_flash *ef, unsigned sector, unsigned page, uint32_t *epoch) {
    uint8_t r[REC_BYTES];
    ef->ops->read(ef->ops->ctx, sector * EPOCH_SECTOR_BYTES + page * EPOCH_PAGE_BYTES, r, sizeof r);
    if (get32(r) != EPOCH_MAGIC || get32(r + 4) != ~get32(r + 8) ||
        get32(r + 12) != epoch_crc32(r, 12))
        return 0;
    *epoch = get32(r + 4);
    return 1;
}

static int page_erased(const epoch_flash *ef, unsigned sector, unsigned page) {
    uint8_t buf[EPOCH_PAGE_BYTES];
    size_t i;
    ef->ops->read(ef->ops->ctx, sector * EPOCH_SECTOR_BYTES + page * EPOCH_PAGE_BYTES, buf,
                  sizeof buf);
    for (i = 0; i < sizeof buf; ++i)
        if (buf[i] != 0xFF) return 0;
    return 1;
}

/* Newest valid record (epoch value) plus where it lives and the next free page of that
 * sector. A page that is neither valid nor erased (torn write) is skipped but consumed. */
typedef struct {
    uint32_t epoch;
    int found;
    unsigned sector, page;
} newest;

static newest scan(const epoch_flash *ef) {
    newest n = {0, 0, 0, 0};
    unsigned s, p;
    for (s = 0; s < 2u; ++s)
        for (p = 0; p < EPOCH_PAGES_PER_SECTOR; ++p) {
            uint32_t e;
            if (read_record(ef, s, p, &e) && (!n.found || e > n.epoch)) {
                n.found = 1;
                n.epoch = e;
                n.sector = s;
                n.page = p;
            }
        }
    return n;
}

void epoch_flash_init(epoch_flash *ef, const epoch_flash_ops *ops) { ef->ops = ops; }

uint32_t epoch_flash_latest(const epoch_flash *ef) {
    newest n = scan(ef);
    return n.found ? n.epoch : 0u;
}

int epoch_flash_load(void *ctx, uint32_t *epoch) {
    const epoch_flash *ef = (const epoch_flash *)ctx;
    if (ef == 0 || ef->ops == 0 || epoch == 0) return -1;
    *epoch = epoch_flash_latest(ef);
    return 0;
}

int epoch_flash_store(void *ctx, uint32_t epoch) {
    const epoch_flash *ef = (const epoch_flash *)ctx;
    uint8_t page[EPOCH_PAGE_BYTES];
    uint32_t back;
    newest n;
    unsigned sector, p, first_free = EPOCH_PAGES_PER_SECTOR;
    if (ef == 0 || ef->ops == 0 || epoch == 0 || epoch == 0xFFFFFFFFu) return -1;
    n = scan(ef);
    if (n.found && epoch <= n.epoch) return -1; /* a counter only moves forward */
    sector = n.found ? n.sector : 0u;
    /* First usable page after the newest record in this sector: erased pages only, so a
     * torn page is never programmed over. */
    for (p = n.found ? n.page + 1u : 0u; p < EPOCH_PAGES_PER_SECTOR; ++p)
        if (page_erased(ef, sector, p)) {
            first_free = p;
            break;
        }
    if (first_free == EPOCH_PAGES_PER_SECTOR) { /* full: roll over to the other sector */
        sector ^= 1u;
        if (ef->ops->erase_sector(ef->ops->ctx, sector) != 0) return -1;
        first_free = 0;
    }
    memset(page, 0xFF, sizeof page);
    put32(page, EPOCH_MAGIC);
    put32(page + 4, epoch);
    put32(page + 8, ~epoch);
    put32(page + 12, epoch_crc32(page, 12));
    if (ef->ops->program_page(ef->ops->ctx, sector, first_free, page) != 0) return -1;
    return (read_record(ef, sector, first_free, &back) && back == epoch) ? 0 : -1;
}
