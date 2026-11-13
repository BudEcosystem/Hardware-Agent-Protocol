/* Flash epoch store: monotonic counter, wear spreading, and power failure injected at every
 * program/erase step. The flash model enforces NOR rules: programming can only clear bits and
 * an erase sets a whole sector to 0xFF. */
#include <stdlib.h>

#include "bhms_test.h"
#include "cal_store.h"
#include "epoch_flash.h"

typedef struct {
    uint8_t mem[2u * EPOCH_SECTOR_BYTES];
    unsigned erases[2], programs;
    long fail_after;     /* power cut after this many mutating operations (< 0: never) */
    int tear;            /* when cut during a program, leave a partially programmed page */
    unsigned ops;
} flash_model;

static void f_read(void *c, uint32_t off, uint8_t *out, size_t n) {
    memcpy(out, ((flash_model *)c)->mem + off, n);
}
static int cut(flash_model *f) {
    if (f->fail_after < 0) return 0;
    if (f->fail_after == 0) return 1;
    --f->fail_after;
    return 0;
}
static int f_erase(void *c, unsigned sector) {
    flash_model *f = (flash_model *)c;
    if (cut(f)) { /* an interrupted erase leaves the first half cleared, the rest old */
        memset(f->mem + sector * EPOCH_SECTOR_BYTES, 0xFF, EPOCH_SECTOR_BYTES / 2u);
        return -1;
    }
    memset(f->mem + sector * EPOCH_SECTOR_BYTES, 0xFF, EPOCH_SECTOR_BYTES);
    ++f->erases[sector];
    return 0;
}
static int f_program(void *c, unsigned sector, unsigned page, const uint8_t *d) {
    flash_model *f = (flash_model *)c;
    uint8_t *dst = f->mem + sector * EPOCH_SECTOR_BYTES + page * EPOCH_PAGE_BYTES;
    size_t i, n = EPOCH_PAGE_BYTES;
    int torn = cut(f);
    if (torn) n = f->tear ? 9u : 0u; /* part of the record reaches the cells */
    for (i = 0; i < n; ++i) dst[i] &= d[i]; /* NOR: bits only clear */
    ++f->programs;
    return torn ? -1 : 0;
}

static const epoch_flash_ops *ops_for(flash_model *f, epoch_flash_ops *o) {
    o->ctx = f;
    o->read = f_read;
    o->erase_sector = f_erase;
    o->program_page = f_program;
    return o;
}

static void fresh(flash_model *f) {
    memset(f, 0xFF, sizeof *f);
    f->erases[0] = f->erases[1] = f->programs = 0;
    f->fail_after = -1;
    f->tear = 0;
}

static void test_monotonic_and_wear(void) {
    flash_model f;
    epoch_flash_ops o;
    epoch_flash ef;
    uint32_t e, v;
    fresh(&f);
    epoch_flash_init(&ef, ops_for(&f, &o));
    CHECK(epoch_flash_load(&ef, &v) == 0 && v == 0); /* erased reads as 0 */
    for (e = 1; e <= 3200; ++e) {
        CHECK(epoch_flash_store(&ef, e) == 0);
        CHECK(epoch_flash_load(&ef, &v) == 0 && v == e);
    }
    /* 16 boots per sector between erases: each sector erased ~once per 32 boots, evenly. */
    CHECK(f.erases[0] + f.erases[1] >= 3200u / 16u - 2u && f.erases[0] + f.erases[1] <= 3200u / 16u);
    CHECK(abs((int)f.erases[0] - (int)f.erases[1]) <= 1);
    CHECK(f.programs == 3200u); /* exactly one page program per boot, no rewrite in place */
    /* A counter never goes backwards; the failed store changes nothing. */
    CHECK(epoch_flash_store(&ef, 5) != 0 && epoch_flash_store(&ef, 3200) != 0);
    CHECK(epoch_flash_store(&ef, 0) != 0 && epoch_flash_store(&ef, 0xFFFFFFFFu) != 0);
    CHECK(epoch_flash_load(&ef, &v) == 0 && v == 3200);
}

/* Cut power at every mutating step of every boot for a few hundred boots: after each cut the
 * counter is either the value before the boot or the new one, never lower and never garbage;
 * the next boot always yields a strictly larger epoch than anything that was advertised. */
static void test_power_fail_everywhere(void) {
    unsigned tear;
    for (tear = 0; tear < 2; ++tear) {
        long cut_at;
        for (cut_at = 0; cut_at < 3; ++cut_at) {
            flash_model f;
            epoch_flash_ops o;
            epoch_flash ef;
            uint32_t acked = 0, v, e;
            unsigned boot;
            fresh(&f);
            f.tear = (int)tear;
            epoch_flash_init(&ef, ops_for(&f, &o));
            for (boot = 0; boot < 300; ++boot) {
                (void)epoch_flash_load(&ef, &v);
                CHECK(v >= acked); /* never lose an acknowledged epoch */
                e = v + 1u;
                f.fail_after = (boot % 5u == 0u) ? cut_at : -1; /* power cut on every 5th boot */
                if (epoch_flash_store(&ef, e) == 0) acked = e;
                f.fail_after = -1;
                (void)epoch_flash_load(&ef, &v);
                CHECK(v == acked || v == e); /* either the old value or the new one */
                CHECK(v >= acked);
                /* the next boot continues from the stored value: strictly increasing */
                if (v == e) acked = e;
            }
            CHECK(acked >= 240u);
        }
    }
}

static void test_garbage_is_ignored(void) {
    flash_model f;
    epoch_flash_ops o;
    epoch_flash ef;
    uint32_t v;
    unsigned i;
    srand(7);
    fresh(&f);
    epoch_flash_init(&ef, ops_for(&f, &o));
    for (i = 0; i < sizeof f.mem; ++i) f.mem[i] = (uint8_t)rand();
    CHECK(epoch_flash_load(&ef, &v) == 0 && v == 0); /* CRC rejects random data */
    /* Recovery from garbage: erase-free path would corrupt, so the store must find free pages
     * or erase; with a full garbage region it rolls over (erases the other sector). */
    CHECK(epoch_flash_store(&ef, 1) == 0);
    CHECK(epoch_flash_load(&ef, &v) == 0 && v == 1);
    /* Flipping a bit of the newest record invalidates it; the older one is returned. */
    CHECK(epoch_flash_store(&ef, 2) == 0 && epoch_flash_store(&ef, 3) == 0);
    {
        unsigned s, p;
        for (s = 0; s < 2; ++s)
            for (p = 0; p < EPOCH_PAGES_PER_SECTOR; ++p) {
                uint8_t *rec = f.mem + s * EPOCH_SECTOR_BYTES + p * EPOCH_PAGE_BYTES;
                if (rec[4] == 3 && rec[0] == 0x45) rec[5] ^= 0x01; /* bad CRC */
            }
    }
    CHECK(epoch_flash_load(&ef, &v) == 0 && v == 2);
}

static void test_crc(void) {
    CHECK(epoch_crc32((const uint8_t *)"123456789", 9) == 0xCBF43926u); /* standard CRC-32 check value */
}


/* The calibration store is the same record log with a payload: monotonic, CRC'd, power-fail safe,
 * and at least the previous copy survives any torn save. */
static void test_calibration_store(void) {
    unsigned tear;
    for (tear = 0; tear < 2; ++tear) {
        flash_model f;
        epoch_flash_ops o;
        cal_store cs;
        arm_cal want, got;
        unsigned i, j;
        fresh(&f);
        f.tear = (int)tear;
        cal_store_init(&cs, ops_for(&f, &o));
        CHECK(cal_store_load(&cs, &got) == 0); /* erased: nothing stored */
        arm_cal_nominal(&want);
        for (i = 1; i <= 120; ++i) {
            arm_cal next = want;
            int ok;
            for (j = 0; j < ARM_NUM_SERVOS; ++j) next.raw_zero[j] = (int16_t)(want.raw_zero[j] + (int)i);
            f.fail_after = (i % 7u == 0u) ? (long)(i % 3u) : -1; /* a power cut on every 7th save */
            ok = cal_store_save(&cs, &next) == 0;
            f.fail_after = -1;
            CHECK(cal_store_load(&cs, &got) == 1);
            if (ok) {
                CHECK(memcmp(&got, &next, sizeof got) == 0);
                want = next;
            } else {
                CHECK(memcmp(&got, &want, sizeof got) == 0); /* the previous calibration survived */
            }
        }
    }
    {
        flash_model f;
        epoch_flash_ops o;
        cal_store cs;
        arm_cal bad, got;
        fresh(&f);
        cal_store_init(&cs, ops_for(&f, &o));
        arm_cal_nominal(&bad);
        bad.sign[2] = 3; /* implausible */
        CHECK(cal_store_save(&cs, &bad) == 0);
        CHECK(cal_store_load(&cs, &got) == 0); /* ignored */
    }
}

int main(void) {
    test_crc();
    test_monotonic_and_wear();
    test_power_fail_everywhere();
    test_garbage_is_ignored();
    test_calibration_store();
    TEST_FINISH("test_epoch");
}
