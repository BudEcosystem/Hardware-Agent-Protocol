#include "epoch_flash.h"

#include <string.h>

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

static size_t rec_len(const reclog *l) { return 8u + l->payload_len; }

/* Returns 1 and the sequence/payload when the page holds a valid record. */
static int read_record(const reclog *l, unsigned sector, unsigned page, uint32_t *seq, uint8_t *payload) {
    uint8_t r[8u + EPOCH_MAX_PAYLOAD + 4u];
    size_t n = rec_len(l);
    l->ops->read(l->ops->ctx, sector * EPOCH_SECTOR_BYTES + page * EPOCH_PAGE_BYTES, r, n + 4u);
    if (get32(r) != l->magic || get32(r + n) != epoch_crc32(r, n)) return 0;
    *seq = get32(r + 4);
    if (payload != 0 && l->payload_len != 0) memcpy(payload, r + 8, l->payload_len);
    return 1;
}

static int page_erased(const reclog *l, unsigned sector, unsigned page) {
    uint8_t buf[EPOCH_PAGE_BYTES];
    size_t i;
    l->ops->read(l->ops->ctx, sector * EPOCH_SECTOR_BYTES + page * EPOCH_PAGE_BYTES, buf, sizeof buf);
    for (i = 0; i < sizeof buf; ++i)
        if (buf[i] != 0xFF) return 0;
    return 1;
}

/* Newest valid record plus where it lives. A page that is neither valid nor erased (torn
 * write) is skipped but consumed. */
typedef struct {
    uint32_t seq;
    int found;
    unsigned sector, page;
} newest;

static newest scan(const reclog *l, uint8_t *payload) {
    newest n = {0, 0, 0, 0};
    unsigned s, p;
    uint8_t tmp[EPOCH_MAX_PAYLOAD];
    for (s = 0; s < 2u; ++s)
        for (p = 0; p < EPOCH_PAGES_PER_SECTOR; ++p) {
            uint32_t e;
            if (read_record(l, s, p, &e, tmp) && (!n.found || e > n.seq)) {
                n.found = 1;
                n.seq = e;
                n.sector = s;
                n.page = p;
                if (payload != 0) memcpy(payload, tmp, l->payload_len);
            }
        }
    return n;
}

void reclog_init(reclog *l, const epoch_flash_ops *ops, uint32_t magic, uint8_t payload_len) {
    l->ops = ops;
    l->magic = magic;
    l->payload_len = payload_len > EPOCH_MAX_PAYLOAD ? EPOCH_MAX_PAYLOAD : payload_len;
}

int reclog_latest(const reclog *l, uint32_t *seq, uint8_t *payload) {
    newest n = scan(l, payload);
    if (n.found) *seq = n.seq;
    return n.found;
}

int reclog_append(const reclog *l, uint32_t seq, const uint8_t *payload) {
    uint8_t page[EPOCH_PAGE_BYTES];
    uint32_t back;
    newest n;
    unsigned sector, p, first_free = EPOCH_PAGES_PER_SECTOR;
    size_t len = rec_len(l);
    if (l->ops == 0 || seq == 0 || seq == 0xFFFFFFFFu) return -1;
    n = scan(l, 0);
    if (n.found && seq <= n.seq) return -1; /* a counter only moves forward */
    sector = n.found ? n.sector : 0u;
    /* First usable page after the newest record in this sector: erased pages only, so a
     * torn page is never programmed over. */
    for (p = n.found ? n.page + 1u : 0u; p < EPOCH_PAGES_PER_SECTOR; ++p)
        if (page_erased(l, sector, p)) {
            first_free = p;
            break;
        }
    if (first_free == EPOCH_PAGES_PER_SECTOR) { /* full: roll over to the other sector */
        sector ^= 1u;
        if (l->ops->erase_sector(l->ops->ctx, sector) != 0) return -1;
        first_free = 0;
    }
    memset(page, 0xFF, sizeof page);
    put32(page, l->magic);
    put32(page + 4, seq);
    if (l->payload_len != 0) memcpy(page + 8, payload, l->payload_len);
    put32(page + len, epoch_crc32(page, len));
    if (l->ops->program_page(l->ops->ctx, sector, first_free, page) != 0) return -1;
    return (read_record(l, sector, first_free, &back, 0) && back == seq) ? 0 : -1;
}

/* ---- Epoch: seq is the epoch itself, no payload ---------------------------------------------- */
void epoch_flash_init(epoch_flash *ef, const epoch_flash_ops *ops) { reclog_init(&ef->log, ops, EPOCH_MAGIC, 0); }

uint32_t epoch_flash_latest(const epoch_flash *ef) {
    uint32_t s = 0;
    return reclog_latest(&ef->log, &s, 0) ? s : 0u;
}

int epoch_flash_load(void *ctx, uint32_t *epoch) {
    const epoch_flash *ef = (const epoch_flash *)ctx;
    if (ef == 0 || ef->log.ops == 0 || epoch == 0) return -1;
    *epoch = epoch_flash_latest(ef);
    return 0;
}

int epoch_flash_store(void *ctx, uint32_t epoch) {
    const epoch_flash *ef = (const epoch_flash *)ctx;
    if (ef == 0 || ef->log.ops == 0) return -1;
    return reclog_append(&ef->log, epoch, 0);
}
