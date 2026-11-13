/* Original finite-bank fault model tests. No EEPROM or target is accessed. */
#include "../protocol/platform/boot_epoch.h"
#include "../protocol/endpoint/endpoint.h"
#include "endpoint_fixture.h"
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t bank[UINT16_MAX + HMS_BOOT_HEADER_BYTES + 8u];
static uint32_t reads, writes, hooks, cut_at, read_fail_at;
static uint8_t fail_write, torn_value, false_success, incarnation_zero;
static jmp_buf power_cut;
static hms_boot_storage storage;
static hms_boot_reservation reservation;
static unsigned checks, cases, cuts, tears;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(2); } } while (0)

static void boundary(void) { ++hooks; if (cut_at != 0u && hooks == cut_at) longjmp(power_cut,1); }
static uint8_t incarnation(void *user, uint8_t index) {
    (void)user;
    return incarnation_zero != 0u ? 0u : (uint8_t)(index + 1u);
}
static uint8_t read_byte(void *user, uint32_t address, uint8_t *value) {
    (void)user;
    boundary(); ++reads;
    CHECK(address < sizeof(bank));
    if (read_fail_at != 0u && reads == read_fail_at) return 0;
    *value = bank[address]; boundary(); return 1;
}
static uint8_t program(void *user, uint32_t address) {
    (void)user;
    boundary(); ++writes;
    CHECK(address >= storage.region_base + HMS_BOOT_HEADER_BYTES && address < sizeof(bank));
    /* The storage contract never programs an already consumed cell. */
    CHECK(bank[address] == 0xffu);
    bank[address] = fail_write != 0u || false_success != 0u ? torn_value : 0u;
    boundary();
    return (uint8_t)(fail_write != 0u ? 0u : 1u);
}
static void counters(void) {
    reads = writes = hooks = cut_at = read_fail_at = 0;
    fail_write = torn_value = false_success = incarnation_zero = 0;
}
static void setup(uint16_t capacity, uint16_t consumed) {
    uint32_t i;
    counters(); memset(bank,0xff,sizeof(bank));
    storage.user = NULL; storage.read_byte = read_byte; storage.program_zero_and_sync = program;
    storage.incarnation_byte = incarnation; storage.region_base = 3; storage.capacity = capacity;
    /* Test-only factory provisioning, outside the reservation API. */
    for (i = 0; i < HMS_BOOT_HEADER_BYTES; ++i)
        bank[storage.region_base + i] = hms_boot_header_byte(&storage,(uint8_t)i);
    for (i = 0; i < consumed; ++i) bank[storage.region_base + HMS_BOOT_HEADER_BYTES + i] = 0;
    hms_boot_init(&reservation);
}
static void reserve(void) { CHECK(hms_boot_acquire(&reservation,&storage) == HMS_BOOT_RESERVED); }

static void sequential_and_latch(void) {
    uint32_t saved_reads, saved_writes;
    uint16_t i;
    setup(8,0);
    for (i=1; i<=8; ++i) {
        hms_boot_init(&reservation); reserve(); CHECK(hms_boot_reserved_epoch(&reservation)==i);
        saved_reads=reads; saved_writes=writes;
        reserve(); CHECK(reads==saved_reads && writes==saved_writes);
    }
    hms_boot_init(&reservation); CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_EXHAUSTED);
    CHECK(hms_boot_reserved_epoch(&reservation)==0 && writes==8);
    ++cases;
}
static void every_torn_byte(void) {
    unsigned value;
    uint16_t prefix;
    for (prefix=0; prefix<7; ++prefix) for (value=0; value<256; ++value) {
        setup(8,prefix); fail_write=1; torn_value=(uint8_t)value;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
        CHECK(hms_boot_reserved_epoch(&reservation)==0);
        fail_write=0; counters(); hms_boot_init(&reservation); reserve();
        CHECK(hms_boot_reserved_epoch(&reservation)==(uint64_t)prefix+(value==255u?1u:2u));
        CHECK(hms_boot_reserved_epoch(&reservation)>prefix); ++tears;
    }
    ++cases;
}
static void every_power_cut_boundary(void) {
    uint32_t bound;
    /* Everything consulted after longjmp is global or assigned afterward. */
    setup(8,2); reserve(); bound=hooks;
    for (cut_at=1; cut_at<=bound; ++cut_at) {
        uint32_t saved_cut=cut_at;
        setup(8,2); cut_at=saved_cut;
        if (setjmp(power_cut)==0) { (void)hms_boot_acquire(&reservation,&storage); CHECK(0); }
        /* The interrupted call never published a returned epoch. A write may
         * already have burned its byte. New boot must exceed released epoch2. */
        saved_cut=cut_at; cut_at=0; hms_boot_init(&reservation); reserve();
        CHECK(hms_boot_reserved_epoch(&reservation)>2u);
        CHECK(hms_boot_reserved_epoch(&reservation)<=4u); ++cuts; cut_at=saved_cut;
    }
    cut_at=0; ++cases;
}
static void every_read_failure(void) {
    uint32_t n;
    for (n=1;n<=HMS_BOOT_HEADER_BYTES+8u+1u;++n) {
        setup(8,2); read_fail_at=n;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
        CHECK(hms_boot_reserved_epoch(&reservation)==0);
        read_fail_at=0; hms_boot_init(&reservation); reserve();
        CHECK(hms_boot_reserved_epoch(&reservation)>2u);
    }
    ++cases;
}
static void every_prefix_pattern(void) {
    unsigned pattern, bit;
    uint8_t seen_erased, valid;
    uint16_t consumed;
    for(pattern=0;pattern<256;++pattern) {
        setup(8,0); seen_erased=0;valid=1;consumed=0;
        for(bit=0;bit<8;++bit) {
            if((pattern&(1u<<bit))!=0u) {
                bank[storage.region_base+HMS_BOOT_HEADER_BYTES+bit]=(uint8_t)(bit+1u);
                ++consumed; if(seen_erased!=0u)valid=0;
            } else seen_erased=1;
        }
        if(valid==0u) CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_NONPREFIX);
        else if(consumed==8u) CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_EXHAUSTED);
        else {reserve();CHECK(hms_boot_reserved_epoch(&reservation)==(uint64_t)consumed+1u);}
        if(valid==0u || consumed==8u)CHECK(writes==0 && hms_boot_reserved_epoch(&reservation)==0);
    }
    ++cases;
}
static void header_and_unprovisioned(void) {
    uint32_t byte;
    for(byte=0;byte<HMS_BOOT_HEADER_BYTES;++byte) {
        setup(8,0); bank[storage.region_base+byte]^=1u;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_HEADER_MISMATCH);
        CHECK(writes==0 && hms_boot_reserved_epoch(&reservation)==0);
    }
    setup(8,0); memset(bank,0xff,sizeof(bank));
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_HEADER_MISMATCH);
    CHECK(writes==0); ++cases;
}
static void invalid_configuration(void) {
    hms_boot_storage other;
    setup(8,0); storage.capacity=0;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    storage.capacity=8; CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    CHECK(reads==0 && writes==0);
    hms_boot_init(&reservation); storage.region_base=UINT32_MAX;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    setup(8,0); incarnation_zero=1;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    setup(8,0); storage.read_byte=NULL;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    setup(8,0); reserve(); other=storage;
    CHECK(hms_boot_acquire(&reservation,&other)==HMS_BOOT_BAD_CONFIG);
    CHECK(hms_boot_acquire(NULL,&storage)==HMS_BOOT_BAD_CONFIG);
    CHECK(hms_boot_reserved_epoch(NULL)==0); ++cases;
}
static void false_write_success(void) {
    setup(8,0); false_success=1;torn_value=0x7f;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_VERIFY_FAILED);
    CHECK(hms_boot_reserved_epoch(&reservation)==0);
    false_success=0;hms_boot_init(&reservation);reserve();
    CHECK(hms_boot_reserved_epoch(&reservation)==2); ++cases;
}
static void maximum_capacity(void) {
    setup(UINT16_MAX,UINT16_MAX-1u); reserve();
    CHECK(hms_boot_reserved_epoch(&reservation)==UINT16_MAX);
    hms_boot_init(&reservation); CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_EXHAUSTED);
    CHECK(writes==1); ++cases;
}
static void endpoint_reset_domain(void) {
    hms_endpoint endpoint; hms_endpoint_fixture fixture; hms_ep_config config;
    uint8_t request[72]={1,16},response[192],index;uint16_t length;
    uint64_t old_boot;
    setup(8,0); reserve();old_boot=hms_boot_reserved_epoch(&reservation);
    hms_endpoint_fixture_init(&fixture,&config);
    CHECK(hms_endpoint_fixture_constant(&fixture,HMS_EP_INCARNATION,"0102030405060708090a0b0c0d0e0f10")==1u);
    for(index=0;index<16u;++index)
        CHECK(config.constant_byte(config.user,HMS_EP_INCARNATION,index)==storage.incarnation_byte(storage.user,index));
    CHECK(hms_endpoint_init(&endpoint,&config,old_boot,1000,25)==1u);
    hms_boot_init(&reservation);reserve();
    CHECK(hms_endpoint_init(&endpoint,&config,hms_boot_reserved_epoch(&reservation),1000,25)==1u);
    request[5]=1;request[7]=1;
    CHECK(hms_endpoint_handle(&endpoint,1,0,old_boot,1,request,72,1000,25,response,&length)==1u);
    CHECK(length==7 && response[6]==HMS_EP_BOOT_MISMATCH);
    CHECK(endpoint.operation_length==0 && endpoint.call_high_water==0);
    ++cases;
}
static void unsupported_rollback_counterexample(void) {
    uint64_t prior;
    setup(8,0);reserve();prior=hms_boot_reserved_epoch(&reservation);
    /* Deliberately violate the persistent-cell assumption. Exact old/erased
     * state is indistinguishable: tests document this LIMIT, not immunity. */
    bank[storage.region_base+HMS_BOOT_HEADER_BYTES]=0xff;
    hms_boot_init(&reservation);reserve();CHECK(hms_boot_reserved_epoch(&reservation)==prior);
    ++cases;
}
int main(void) {
    sequential_and_latch();every_torn_byte();every_power_cut_boundary();every_read_failure();
    every_prefix_pattern();header_and_unprovisioned();invalid_configuration();false_write_success();
    maximum_capacity();endpoint_reset_domain();unsupported_rollback_counterexample();
    printf("{\"cases\":%u,\"assertions\":%u,\"torn_byte_cases\":%u,\"power_cut_boundaries\":%u,\"rollback_counterexample_demonstrated\":true,\"reservation_bytes\":%zu,\"storage_config_bytes\":%zu}\n",cases,checks,tears,cuts,sizeof(reservation),sizeof(storage));
    return 0;
}
