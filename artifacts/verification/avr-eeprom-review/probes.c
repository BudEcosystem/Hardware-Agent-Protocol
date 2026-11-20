/* Independent original host register shim. No target/silicon/electrical model. */
#include "avr_eeprom.h"
#include "boot_epoch.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct {
    uint8_t cells[1024], sreg, saved, pending, final_value;
    uint16_t selected, write_address;
    unsigned checks, spm_checks, enters, exits, addresses, reads, launches;
    unsigned initial_busy, completion_busy, inject_at;
    uint8_t inject_control, inject_spm, reenter;
    hms_avr_eeprom *driver;
} model;
static unsigned assertions, cases, sreg_patterns, budget_scenarios, readback_values;
#define CHECK(x) do { ++assertions; if(!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(2); } } while(0)

static void reset(uint8_t sreg) {
    memset(&model,0,sizeof(model));memset(model.cells,0xff,sizeof(model.cells));model.sreg=sreg;
}
uint8_t hms_avr_probe_control(void) {
    uint8_t value=0;
    ++model.checks;
    if(model.initial_busy!=0u){--model.initial_busy;value|=2u;}
    if(model.pending!=0u) {
        if(model.completion_busy!=0u){--model.completion_busy;value|=2u;}
        else {model.cells[model.write_address]=model.final_value;model.pending=0;}
    }
    if(model.checks==model.inject_at)value|=model.inject_control;
    return value;
}
uint8_t hms_avr_probe_spm(void) {
    ++model.spm_checks;
    return model.checks==model.inject_at ? model.inject_spm : 0u;
}
uint8_t hms_avr_probe_save_cli(void) {
    CHECK(model.enters==model.exits);++model.enters;
    model.saved=model.sreg;model.sreg&=0x7fu;
    return model.saved;
}
void hms_avr_probe_restore(uint8_t saved) {
    CHECK(model.enters==model.exits+1u && saved==model.saved);
    if(model.reenter!=0u) {
        uint8_t value=0x6a, old_status=model.driver->last_status;
        CHECK(model.driver->active==1u);
        CHECK(hms_avr_eeprom_read_byte(model.driver,0,&value)==0u);
        CHECK(hms_avr_eeprom_read_byte(model.driver,UINT32_MAX,NULL)==0u);
        CHECK(hms_avr_eeprom_program_zero_and_sync(model.driver,UINT32_MAX)==0u);
        CHECK(value==0x6a && model.driver->last_status==old_status);
    }
    model.sreg=saved;++model.exits;
}
void hms_avr_probe_address(uint16_t address) {
    CHECK(address<1024u && model.pending==0u);
    CHECK((model.sreg&0x80u)==0u && model.enters==model.exits+1u);
    model.selected=address;++model.addresses;
}
uint8_t hms_avr_probe_read(void) {
    CHECK(model.pending==0u && (model.sreg&0x80u)==0u);
    CHECK(model.enters==model.exits+1u);++model.reads;
    return model.cells[model.selected];
}
void hms_avr_probe_launch_zero(void) {
    CHECK(model.pending==0u && (model.sreg&0x80u)==0u);
    CHECK(model.enters==model.exits+1u && model.cells[model.selected]==0xffu);
    model.write_address=model.selected;model.pending=1;++model.launches;
}
static void balanced(const hms_avr_eeprom *d,uint8_t saved) {
    CHECK(model.sreg==saved && model.enters==model.exits && d->active==0u);
}

static void complete_sreg_and_masked_failures(void) {
    unsigned sreg,kind;
    hms_avr_eeprom d;
    for(sreg=0;sreg<256u;++sreg) {
        uint8_t value=0;
        reset((uint8_t)sreg);hms_avr_eeprom_init(&d,2);model.cells[1023]=0x9a;
        CHECK(hms_avr_eeprom_read_byte(&d,1023,&value)==1u && value==0x9a);
        CHECK(model.checks==2 && model.launches==0);balanced(&d,(uint8_t)sreg);
        reset((uint8_t)sreg);hms_avr_eeprom_init(&d,4);
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d,1023)==1u);
        CHECK(model.cells[1023]==0 && model.checks==4 && model.launches==1);balanced(&d,(uint8_t)sreg);
        for(kind=0;kind<3u;++kind) {
            reset((uint8_t)sreg);hms_avr_eeprom_init(&d,8);model.inject_at=2;
            model.inject_control=kind==0u?2u:kind==1u?8u:0u;model.inject_spm=kind==2u?1u:0u;
            CHECK(hms_avr_eeprom_program_zero_and_sync(&d,0)==0u);
            CHECK(d.last_status==HMS_AVR_EEPROM_OWNER_CONFLICT && model.launches==0 && model.addresses==0);
            balanced(&d,(uint8_t)sreg);
        }
        ++sreg_patterns;
    }
    ++cases;
}
static void one_budget_across_write(void) {
    unsigned before,after,budget;
    hms_avr_eeprom d;
    for(before=0;before<6u;++before)for(after=0;after<6u;++after) {
        unsigned need=before+after+4u;
        for(budget=1;budget<=need+1u;++budget) {
            reset(0xd5);hms_avr_eeprom_init(&d,(uint16_t)budget);
            model.initial_busy=before;model.completion_busy=after;
            CHECK(hms_avr_eeprom_program_zero_and_sync(&d,511)==(budget>=need?1u:0u));
            CHECK(model.checks==(budget<need?budget:need));
            CHECK(model.launches==(budget>=before+2u?1u:0u));
            CHECK((model.cells[511]==0u)==(budget>=before+after+3u));
            CHECK(d.last_status==(budget>=need?HMS_AVR_EEPROM_OK:HMS_AVR_EEPROM_BUSY_TIMEOUT));
            balanced(&d,0xd5);++budget_scenarios;
        }
    }
    reset(0xa5);hms_avr_eeprom_init(&d,UINT16_MAX);model.initial_busy=UINT16_MAX;
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d,0)==0u);
    CHECK(model.checks==UINT16_MAX && model.enters==0 && model.launches==0);
    balanced(&d,0xa5);++cases;
}
static void post_launch_races_and_readback(void) {
    unsigned kind,value;
    hms_avr_eeprom d;
    for(kind=0;kind<3u;++kind) {
        reset(0xff);hms_avr_eeprom_init(&d,8);model.inject_at=4;
        model.inject_control=kind==0u?2u:kind==1u?8u:0u;model.inject_spm=kind==2u?1u:0u;
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d,19)==0u);
        CHECK(d.last_status==HMS_AVR_EEPROM_OWNER_CONFLICT && model.launches==1);
        CHECK(model.cells[19]==0 && model.addresses==1 && model.reads==1);
        balanced(&d,0xff);
    }
    reset(0x55);hms_avr_eeprom_init(&d,8);model.inject_at=3;model.inject_control=8;
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d,19)==0u);
    CHECK(d.last_status==HMS_AVR_EEPROM_OWNER_CONFLICT && model.cells[19]==0 && model.launches==1);
    balanced(&d,0x55);
    for(value=1;value<256u;++value) {
        reset(0x73);hms_avr_eeprom_init(&d,4);model.final_value=(uint8_t)value;
        CHECK(hms_avr_eeprom_program_zero_and_sync(&d,1000)==0u);
        CHECK(d.last_status==HMS_AVR_EEPROM_VERIFY_FAILED && model.cells[1000]==value && model.launches==1);
        balanced(&d,0x73);++readback_values;
    }
    ++cases;
}
static void reentry_at_restore(void) {
    hms_avr_eeprom d;
    reset(0xbd);hms_avr_eeprom_init(&d,4);model.driver=&d;model.reenter=1;
    CHECK(hms_avr_eeprom_program_zero_and_sync(&d,7)==1u);
    CHECK(model.launches==1 && model.checks==4 && d.last_status==HMS_AVR_EEPROM_OK);
    balanced(&d,0xbd);++cases;
}
static uint8_t incarnation(void *user,uint8_t index) {
    (void)user;CHECK(index<16u);return (uint8_t)(index+1u);
}
static void bank_failure_latch(void) {
    hms_avr_eeprom d;
    hms_boot_reservation reservation;
    hms_boot_storage bank;
    unsigned i,saved_checks,saved_launches;
    reset(0xa6);hms_avr_eeprom_init(&d,3);
    /* Independent literal factory header for capacity2 and incarnation01..10. */
    memcpy(model.cells,"HMSBOOT1",8);
    for(i=0;i<16u;++i)model.cells[8u+i]=(uint8_t)(i+1u);
    model.cells[24]=0;model.cells[25]=2;memset(model.cells+26,0,6);
    bank.user=&d;bank.read_byte=hms_avr_eeprom_read_byte;bank.program_zero_and_sync=hms_avr_eeprom_program_zero_and_sync;
    bank.incarnation_byte=incarnation;bank.region_base=0;bank.capacity=2;
    hms_boot_init(&reservation);
    CHECK(hms_boot_acquire(&reservation,&bank)==HMS_BOOT_STORAGE_ERROR);
    CHECK(hms_boot_reserved_epoch(&reservation)==0 && model.cells[32]==0 && model.launches==1);
    CHECK(d.last_status==HMS_AVR_EEPROM_BUSY_TIMEOUT);balanced(&d,0xa6);
    saved_checks=model.checks;saved_launches=model.launches;
    CHECK(hms_boot_acquire(&reservation,&bank)==HMS_BOOT_STORAGE_ERROR);
    CHECK(model.checks==saved_checks && model.launches==saved_launches);
    /* Simulated next startup: permit a larger immutable per-callback budget. */
    hms_boot_init(&reservation);hms_avr_eeprom_init(&d,4);
    CHECK(hms_boot_acquire(&reservation,&bank)==HMS_BOOT_RESERVED);
    CHECK(hms_boot_reserved_epoch(&reservation)==2u && model.cells[33]==0 && model.launches==2);
    balanced(&d,0xa6);++cases;
}
int main(void) {
    complete_sreg_and_masked_failures();one_budget_across_write();post_launch_races_and_readback();
    reentry_at_restore();bank_failure_latch();
    printf("{\"cases\":%u,\"assertions\":%u,\"sreg_patterns\":%u,\"write_budget_scenarios\":%u,\"nonzero_readback_values\":%u,\"target_executed\":false}\n",
           cases,assertions,sreg_patterns,budget_scenarios,readback_values);
    return 0;
}
