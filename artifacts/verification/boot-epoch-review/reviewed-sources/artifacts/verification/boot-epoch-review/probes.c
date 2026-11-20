/* Independent original native probes. No EEPROM, peripheral or target runs. */
#include "boot_epoch.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t bytes[HMS_BOOT_HEADER_BYTES + UINT16_MAX];
static hms_boot_storage storage;
static hms_boot_reservation reservation;
static uint32_t reads, programs, incarnation_reads, reentries;
static uint32_t fail_read;
static uint8_t read_status, program_status, programmed_value, reenter;
static unsigned checks, cases;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(2); } } while(0)

static void reentry(uint8_t phase) {
    if (reenter == phase) {
        hms_boot_storage other = storage;
        ++reentries;
        CHECK(hms_boot_reserved_epoch(&reservation) == 0u);
        CHECK(hms_boot_acquire(&reservation, &storage) == HMS_BOOT_IN_PROGRESS);
        CHECK(hms_boot_acquire(&reservation, &other) == HMS_BOOT_BAD_CONFIG);
        CHECK(hms_boot_reserved_epoch(&reservation) == 0u);
    }
}
static uint8_t incarnation(void *user, uint8_t index) {
    (void)user; CHECK(index < 16u); ++incarnation_reads; reentry(3);
    return (uint8_t)(0xa0u + index);
}
static uint32_t offset(uint32_t address) {
    CHECK(address >= storage.region_base);
    CHECK(address - storage.region_base < HMS_BOOT_HEADER_BYTES + (uint32_t)storage.capacity);
    return address - storage.region_base;
}
static uint8_t read_byte(void *user, uint32_t address, uint8_t *value) {
    uint32_t index = offset(address);
    (void)user; CHECK(value != NULL); ++reads; reentry(1);
    if (reads == fail_read) return read_status;
    *value = bytes[index]; return 1;
}
static uint8_t program(void *user, uint32_t address) {
    uint32_t index = offset(address);
    (void)user; CHECK(index >= HMS_BOOT_HEADER_BYTES);
    CHECK(bytes[index] == 0xffu); ++programs; reentry(2);
    bytes[index] = programmed_value; return program_status;
}
static void setup(uint16_t capacity, uint32_t base) {
    static const uint8_t magic[8] = {0x48,0x4d,0x53,0x42,0x4f,0x4f,0x54,0x31};
    unsigned i;
    memset(bytes, 0xff, sizeof(bytes));
    /* Independent literal format oracle; never provision via the API helper. */
    memcpy(bytes, magic, sizeof(magic));
    for (i=0;i<16u;++i) bytes[8u+i]=(uint8_t)(0xa0u+i);
    bytes[24]=(uint8_t)(capacity>>8);bytes[25]=(uint8_t)capacity;
    memset(bytes+26,0,6);
    storage.user=NULL;storage.read_byte=read_byte;storage.program_zero_and_sync=program;
    storage.incarnation_byte=incarnation;storage.capacity=capacity;storage.region_base=base;
    reads=programs=incarnation_reads=reentries=fail_read=0;
    read_status=0;program_status=1;programmed_value=0;reenter=0;
    hms_boot_init(&reservation);
}
static void same_attempt_is_latched(uint8_t status) {
    uint32_t old_reads=reads, old_programs=programs, old_incarnation=incarnation_reads;
    CHECK(hms_boot_acquire(&reservation,&storage)==status);
    CHECK(reads==old_reads && programs==old_programs && incarnation_reads==old_incarnation);
}
static void header_oracle(void) {
    unsigned i;
    setup(0x0102u,0);
    for(i=0;i<HMS_BOOT_HEADER_BYTES;++i) CHECK(hms_boot_header_byte(&storage,(uint8_t)i)==bytes[i]);
    CHECK(hms_boot_header_byte(NULL,0)==0);
    CHECK(hms_boot_header_byte(&storage,32)==0 && hms_boot_header_byte(&storage,255)==0);
    storage.incarnation_byte=NULL;CHECK(hms_boot_header_byte(&storage,8)==0);
    ++cases;
}
static void null_and_bad_configuration(void) {
    unsigned variant;
    hms_boot_init(NULL);
    CHECK(hms_boot_acquire(NULL,NULL)==HMS_BOOT_BAD_CONFIG);
    CHECK(hms_boot_reserved_epoch(NULL)==0);
    setup(1,0);CHECK(hms_boot_reserved_epoch(&reservation)==0);
    CHECK(hms_boot_acquire(&reservation,NULL)==HMS_BOOT_BAD_CONFIG);
    CHECK(hms_boot_acquire(&reservation,NULL)==HMS_BOOT_BAD_CONFIG);
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
    CHECK(reads==0 && programs==0 && incarnation_reads==0);
    for(variant=0;variant<4u;++variant) {
        setup(1,0);
        if(variant==0)storage.read_byte=NULL;
        if(variant==1)storage.program_zero_and_sync=NULL;
        if(variant==2)storage.incarnation_byte=NULL;
        if(variant==3)storage.capacity=0;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
        CHECK(hms_boot_reserved_epoch(&reservation)==0);
        same_attempt_is_latched(HMS_BOOT_BAD_CONFIG);
        CHECK(reads==0 && programs==0 && incarnation_reads==0);
    }
    ++cases;
}
static void upper_address_boundaries(void) {
    uint32_t maximum_base;
    uint16_t capacities[3]={1u,2u,UINT16_MAX};
    unsigned i;
    for(i=0;i<3u;++i) {
        maximum_base=UINT32_MAX-HMS_BOOT_HEADER_BYTES-((uint32_t)capacities[i]-1u);
        setup(capacities[i],maximum_base);
        memset(bytes+HMS_BOOT_HEADER_BYTES,0,(size_t)capacities[i]-1u);
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_RESERVED);
        CHECK(hms_boot_reserved_epoch(&reservation)==capacities[i]);
        CHECK(programs==1);
        same_attempt_is_latched(HMS_BOOT_RESERVED);
        hms_boot_init(&reservation);
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_EXHAUSTED);
        CHECK(hms_boot_reserved_epoch(&reservation)==0 && programs==1);
        setup(capacities[i],maximum_base+1u);
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_BAD_CONFIG);
        CHECK(reads==0 && programs==0 && incarnation_reads==0);
    }
    ++cases;
}
static void invalid_callback_returns_and_postwrite_failure(void) {
    unsigned status;
    for(status=0;status<256u;++status) {
        if(status==1u)continue;
        setup(2,0);fail_read=1;read_status=(uint8_t)status;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
        CHECK(hms_boot_reserved_epoch(&reservation)==0 && programs==0);
        same_attempt_is_latched(HMS_BOOT_STORAGE_ERROR);
        setup(2,0);program_status=(uint8_t)status;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
        CHECK(hms_boot_reserved_epoch(&reservation)==0 && programs==1);
        same_attempt_is_latched(HMS_BOOT_STORAGE_ERROR);
        hms_boot_init(&reservation);program_status=1;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_RESERVED);
        CHECK(hms_boot_reserved_epoch(&reservation)==2u);
    }
    setup(2,0);fail_read=HMS_BOOT_HEADER_BYTES+2u+1u;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
    CHECK(programs==1 && bytes[HMS_BOOT_HEADER_BYTES]==0 && hms_boot_reserved_epoch(&reservation)==0);
    same_attempt_is_latched(HMS_BOOT_STORAGE_ERROR);
    hms_boot_init(&reservation);fail_read=0;
    CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_RESERVED);
    CHECK(hms_boot_reserved_epoch(&reservation)==2u);
    ++cases;
}
static void all_last_cell_tears(void) {
    unsigned value;
    for(value=0;value<256u;++value) {
        setup(3,0);bytes[32]=bytes[33]=0;program_status=0;programmed_value=(uint8_t)value;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_STORAGE_ERROR);
        CHECK(hms_boot_reserved_epoch(&reservation)==0);
        same_attempt_is_latched(HMS_BOOT_STORAGE_ERROR);
        hms_boot_init(&reservation);program_status=1;programmed_value=0;
        if(value==255u) {
            CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_RESERVED);
            CHECK(hms_boot_reserved_epoch(&reservation)==3u);
        } else {
            CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_EXHAUSTED);
            CHECK(hms_boot_reserved_epoch(&reservation)==0);
        }
    }
    ++cases;
}
static void callback_reentry_does_not_publish(void) {
    uint8_t phase;
    for(phase=1;phase<=3u;++phase) {
        hms_boot_storage other;
        setup(2,0);reenter=phase;
        CHECK(hms_boot_acquire(&reservation,&storage)==HMS_BOOT_RESERVED);
        CHECK(reentries>0 && programs==1 && hms_boot_reserved_epoch(&reservation)==1u);
        same_attempt_is_latched(HMS_BOOT_RESERVED);
        other=storage;CHECK(hms_boot_acquire(&reservation,&other)==HMS_BOOT_BAD_CONFIG);
        CHECK(hms_boot_reserved_epoch(&reservation)==1u);
    }
    ++cases;
}
int main(void) {
    header_oracle();null_and_bad_configuration();upper_address_boundaries();
    invalid_callback_returns_and_postwrite_failure();all_last_cell_tears();callback_reentry_does_not_publish();
    printf("{\"cases\":%u,\"assertions\":%u,\"last_cell_torn_values\":256,\"non_success_callback_values\":255,\"physical_qualification\":false}\n",cases,checks);
    return 0;
}
