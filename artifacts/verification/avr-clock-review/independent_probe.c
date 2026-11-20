/* Independent native register/history oracle, written for review.
 * Not an AVR emulator, instruction model, device driver or timing test. */
#include "avr_clock.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { A, B, C, MASK, FLAG, LOW, HIGH, POWER, PRESCALE, SYNC };
static uint8_t registers[10], latch, status, saved_status[4];
static uint64_t truth, captures[4];
static uint8_t increments[24];
static unsigned depth, accesses, captured, writes, schedule_on, restore_action, entry_action;
static unsigned phase, case_id, force_flag_drop;
static uint64_t assertions, timelines, arithmetic, sequence_steps, boundary_cases, aliases;
static hms_avr_clock c;
static const uint64_t epoch = UINT64_C(0x1122334455667788);
#define REQUIRE(x) do { ++assertions; if (!(x)) { \
  fprintf(stderr,"phase=%u case=%u line=%u: %s\n",phase,case_id,(unsigned)__LINE__,#x); exit(11); \
} } while (0)

static void tick(uint32_t count) {
    uint64_t next = truth + count;
    if ((next >> 16) != (truth >> 16)) registers[FLAG] |= 1u;
    truth = next;
}
static void interrupt(void) {
    uint8_t prior = status;
    REQUIRE(depth == 0u && (status & 0x80u) && (registers[MASK] & 1u) && (registers[FLAG] & 1u));
    status &= 0x7fu; registers[FLAG] &= 0xfeu;
    hms_avr_clock_overflow(&c);
    REQUIRE(depth == 0u && !(status & 0x80u));
    status = prior;
}
uint8_t hms_avr_clock_probe_save_cli(void) {
    uint8_t prior = status;
    if (entry_action) { entry_action = 0u; tick(1u); interrupt(); }
    REQUIRE(depth < 4u); saved_status[depth++] = prior;
    status &= 0x7fu;
    return prior;
}
void hms_avr_clock_probe_restore(uint8_t prior) {
    REQUIRE(depth != 0u && prior == saved_status[depth - 1u]);
    --depth; status = prior;
    if (restore_action) {
        unsigned action = restore_action; restore_action = 0u;
        if (action == 1u) { tick(1u); interrupt(); }
        else hms_avr_clock_invalidate(&c);
    }
}
uint8_t hms_avr_clock_probe_read(uint8_t reg) {
    REQUIRE(depth == 1u && !(status & 0x80u) && reg < 10u);
    unsigned position = 2u * accesses++;
    if (schedule_on && position < 24u) tick(increments[position]);
    uint8_t value;
    if (reg == LOW) {
        REQUIRE(captured < 4u); captures[captured++] = truth;
        value = (uint8_t)truth; latch = (uint8_t)(truth >> 8);
    } else if (reg == HIGH) value = latch;
    else { value = registers[reg]; if (reg == FLAG && force_flag_drop) { registers[FLAG] &= 0xfeu; force_flag_drop = 0u; } }
    if (schedule_on && position + 1u < 24u) tick(increments[position + 1u]);
    return value;
}
void hms_avr_clock_probe_write(uint8_t reg, uint8_t value) {
    REQUIRE(depth == 1u && !(status & 0x80u) && reg < 10u);
    ++writes;
    if (reg == HIGH) latch = value;
    else if (reg == LOW) truth = ((uint64_t)latch << 8) | value;
    else if (reg == FLAG) registers[FLAG] &= (uint8_t)~value;
    else registers[reg] = value;
}
static void reset(void) {
    REQUIRE(depth == 0u);
    memset(registers,0,sizeof(registers)); memset(increments,0,sizeof(increments));
    truth = 0u; status = 0xd5u; latch = 0x5au;
    accesses = captured = writes = schedule_on = restore_action = entry_action = force_flag_drop = 0u;
    hms_avr_clock_init(&c,epoch);
}
static void ready(uint64_t raw, uint32_t accounted) {
    reset();
    REQUIRE(hms_avr_clock_start(&c) == HMS_AVR_CLOCK_UNQUALIFIED);
    REQUIRE(hms_avr_clock_qualify(&c,epoch,HMS_AVR_CLOCK_ALL_ASSURED) == HMS_AVR_CLOCK_OK);
    truth = raw; c.wraps = accounted; registers[FLAG] = (uint8_t)((raw >> 16) != accounted);
    accesses = captured = 0u;
}
static hms_avr_clock_result read_checked(hms_avr_clock_sample *sample) {
    hms_avr_clock_sample prior = *sample;
    uint8_t prior_status = status;
    unsigned old_writes = writes;
    hms_avr_clock_result result = hms_avr_clock_read(&c,sample);
    REQUIRE(depth == 0u && status == prior_status && writes == old_writes);
    if (result != HMS_AVR_CLOCK_OK) REQUIRE(memcmp(sample,&prior,sizeof(prior)) == 0);
    else {
        REQUIRE(sample->boot_epoch == epoch && sample->raw_tick <= HMS_AVR_CLOCK_RAW_MAX);
        REQUIRE(sample->tick_ms == sample->raw_tick / UINT64_C(250));
    }
    return result;
}
static void timeline(uint64_t initial, uint32_t accounted, unsigned pattern) {
    ready(initial,accounted);
    /* Exhaust all 12 before/after slots of the six potential timer reads.
     * Configuration reads remain stable. Unreached reread slots are inert. */
    for (unsigned j=0u;j<12u;++j) increments[j+12u]=(uint8_t)((pattern>>j)&1u);
    schedule_on=1u;
    hms_avr_clock_sample out={0u,0u,0u};
    REQUIRE(read_checked(&out) == HMS_AVR_CLOCK_OK);
    REQUIRE(out.raw_tick >= initial && out.raw_tick <= truth && c.wraps == accounted);
    unsigned matched=0u;
    for (unsigned j=0u;j<captured;++j) if (captures[j] == out.raw_tick) matched=1u;
    REQUIRE(matched && captured >= 1u && captured <= 2u);
    schedule_on=0u;
    uint64_t prior=out.raw_tick;
    if (registers[FLAG]&1u) interrupt();
    accesses=captured=0u;
    REQUIRE(read_checked(&out) == HMS_AVR_CLOCK_OK && out.raw_tick == truth && out.raw_tick >= prior);
    ++timelines;
}
static void timeline_sweep(void) {
    phase=1u;
    const uint16_t starts[]={254u,255u,65524u,65525u,65526u,65527u,65528u,65529u,
                            65530u,65531u,65532u,65533u,65534u,65535u};
    for (unsigned i=0u;i<sizeof(starts)/sizeof(starts[0]);++i)
        for (unsigned p=0u;p<4096u;++p) { case_id=i*4096u+p; timeline((UINT64_C(7)<<16)|starts[i],7u,p); }
    /* Initial pending flag; high byte latching and half-period vicinity remain
     * strictly inside the installation service bound throughout the read. */
    const uint16_t pending[]={0u,1u,254u,255u,32740u,32750u};
    for(unsigned i=0u;i<sizeof(pending)/sizeof(pending[0]);++i)
        for(unsigned p=0u;p<4096u;++p) { case_id=60000u+i*4096u+p; timeline((UINT64_C(8)<<16)|pending[i],7u,p); }
}
static uint32_t random_next(uint32_t *state) {
    *state=*state*UINT32_C(1664525)+UINT32_C(1013904223); return *state;
}
static void random_timeline(void) {
    phase=2u; uint32_t rng=UINT32_C(0x6bf5a129);
    for(unsigned n=0u;n<50000u;++n) {
        case_id=n; uint32_t h=random_next(&rng) & UINT32_C(0x7fffffff);
        uint16_t low=(uint16_t)(UINT16_MAX-(random_next(&rng)%64u));
        uint64_t begin=((uint64_t)h<<16)|low; ready(begin,h);
        for(unsigned j=0u;j<24u;++j) increments[j]=(uint8_t)(random_next(&rng)%8u);
        schedule_on=1u; hms_avr_clock_sample out={0u,0u,0u};
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick>=begin && out.raw_tick<=truth);
        unsigned matched=0u;
        for(unsigned j=0u;j<captured;++j) if(captures[j]==out.raw_tick) matched=1u;
        REQUIRE(matched && c.wraps==h); schedule_on=0u;
        if(registers[FLAG]&1u) interrupt();
        accesses=captured=0u;
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==truth);
        ++timelines;
    }
}
static void conversion_sweep(void) {
    phase=3u; hms_avr_clock_sample out={0u,0u,0u};
    /* All 125 residual high words x all 65536 low words. Direct 64-bit division
     * is independent of the implementation's quotient/remainder decomposition. */
    for(uint32_t h=0u;h<125u;++h) {
        ready((uint64_t)h<<16,h);
        for(uint32_t low=0u;low<=UINT16_MAX;++low) {
            case_id=low; truth=((uint64_t)h<<16)|low; accesses=captured=0u;
            REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==truth); ++arithmetic;
        }
    }
    const uint32_t high[]={125u,126u,65535u,65536u,UINT32_C(0x7fffffff),UINT32_C(0x80000000),UINT32_MAX};
    const uint16_t low[]={0u,1u,249u,250u,251u,32767u,32768u,65535u};
    for(unsigned h=0u;h<sizeof(high)/sizeof(high[0]);++h)
        for(unsigned l=0u;l<sizeof(low)/sizeof(low[0]);++l) {
            case_id=h*10u+l; ready(((uint64_t)high[h]<<16)|low[l],high[h]);
            REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==truth); ++arithmetic;
        }
}
static void lifecycle_and_faults(void) {
    phase=4u; hms_avr_clock_sample out;
    memset(&out,0xa6,sizeof(out)); reset();
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_UNQUALIFIED);
    REQUIRE(hms_avr_clock_start(&c)==HMS_AVR_CLOCK_UNQUALIFIED);
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_UNQUALIFIED);
    for(unsigned grant=0u;grant<=255u;++grant) {
        case_id=grant; reset(); REQUIRE(hms_avr_clock_start(&c)==HMS_AVR_CLOCK_UNQUALIFIED);
        REQUIRE(hms_avr_clock_qualify(&c,epoch,(uint8_t)grant)==(grant==7u?HMS_AVR_CLOCK_OK:HMS_AVR_CLOCK_FAULT));
        if(grant!=7u) {
            REQUIRE(c.fault==HMS_AVR_CLOCK_BAD_GRANT && !c.qualified);
            REQUIRE(hms_avr_clock_qualify(&c,epoch,7u)==HMS_AVR_CLOCK_FAULT);
            REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT);
        }
        ++boundary_cases;
    }
    reset(); REQUIRE(hms_avr_clock_qualify(&c,epoch,7u)==HMS_AVR_CLOCK_FAULT);
    ready(500u,0u); REQUIRE(hms_avr_clock_qualify(&c,epoch+1u,7u)==HMS_AVR_CLOCK_FAULT);
    ready(500u,0u); hms_avr_clock_invalidate(&c);
    REQUIRE(hms_avr_clock_qualify(&c,epoch,7u)==HMS_AVR_CLOCK_FAULT && c.fault==HMS_AVR_CLOCK_DISCONTINUITY);
    unsigned before=writes;
    REQUIRE(hms_avr_clock_start(&c)==HMS_AVR_CLOCK_FAULT && writes==before);
    REQUIRE((c.fault & (HMS_AVR_CLOCK_RESTART|HMS_AVR_CLOCK_DISCONTINUITY))==(HMS_AVR_CLOCK_RESTART|HMS_AVR_CLOCK_DISCONTINUITY));
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT);
    for(unsigned n=0u;n<2u;++n) {
        reset(); hms_avr_clock_init(&c,n?UINT64_MAX:0u);
        REQUIRE(hms_avr_clock_start(&c)==HMS_AVR_CLOCK_FAULT && !writes && c.fault==HMS_AVR_CLOCK_BAD_BOOT);
    }
    /* All saved status patterns, including calls beginning with I already clear. */
    for(unsigned s=0u;s<256u;++s) {
        case_id=s; ready(1234u,0u); status=(uint8_t)s;
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && status==s);
        hms_avr_clock_invalidate(&c); REQUIRE(status==s && read_checked(&out)==HMS_AVR_CLOCK_FAULT);
        ++boundary_cases;
    }
    const uint8_t bad_reg[]={A,B,MASK,POWER,PRESCALE,SYNC,SYNC};
    const uint8_t bad_value[]={1u,1u,3u,8u,1u,1u,128u};
    for(unsigned i=0u;i<sizeof(bad_reg);++i) {
        ready(100u,0u); uint8_t old=registers[bad_reg[i]]; registers[bad_reg[i]]=bad_value[i];
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT && c.fault==HMS_AVR_CLOCK_CONFIG);
        registers[bad_reg[i]]=old; REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT);
        ++boundary_cases;
    }
}
static void late_exhaustion_and_restore(void) {
    phase=5u; hms_avr_clock_sample out={0u,0u,0u};
    const uint16_t lows[]={32766u,32767u,32768u,32769u,65535u};
    for(unsigned i=0u;i<sizeof(lows)/sizeof(lows[0]);++i) {
        case_id=i; ready((UINT64_C(8)<<16)|lows[i],7u);
        REQUIRE(read_checked(&out)==(lows[i]<32768u?HMS_AVR_CLOCK_OK:HMS_AVR_CLOCK_FAULT));
        if(lows[i]>=32768u) REQUIRE(c.fault==HMS_AVR_CLOCK_LATE);
        ready((UINT64_C(8)<<16)|lows[i],7u); interrupt();
        REQUIRE(c.fault==(lows[i]<32768u?0u:HMS_AVR_CLOCK_LATE));
        REQUIRE(c.wraps==(lows[i]<32768u?8u:7u)); ++boundary_cases;
    }
    ready(UINT64_C(8)<<16,7u); hms_avr_clock_overflow(&c);
    REQUIRE(c.fault==HMS_AVR_CLOCK_LATE && c.wraps==7u);
    ready(UINT64_C(8)<<16,7u); force_flag_drop=1u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT && c.fault==HMS_AVR_CLOCK_CONFIG);
    ready(HMS_AVR_CLOCK_RAW_MAX,UINT32_MAX);
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==HMS_AVR_CLOCK_RAW_MAX);
    tick(1u); accesses=captured=0u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT && c.fault==HMS_AVR_CLOCK_EXHAUSTED);
    ready(HMS_AVR_CLOCK_RAW_MAX,UINT32_MAX); tick(1u); interrupt();
    REQUIRE(c.fault==HMS_AVR_CLOCK_EXHAUSTED && c.wraps==UINT32_MAX);
    ready(100u,0u); REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK);
    truth=99u; accesses=captured=0u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT && c.fault==HMS_AVR_CLOCK_REGRESSION);
    ready(UINT64_C(65535),0u); entry_action=1u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==65536u && c.wraps==1u);
    ready(UINT64_C(65535),0u); restore_action=1u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==65535u && c.wraps==1u);
    ready(100u,0u); restore_action=2u;
    REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==100u && c.fault==HMS_AVR_CLOCK_DISCONTINUITY);
    accesses=captured=0u; REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT);
    boundary_cases+=10u;
}
static void long_sequences(void) {
    phase=6u; uint32_t rng=UINT32_C(0x15939c31); hms_avr_clock_sample out={0u,0u,0u};
    ready(0u,0u);
    uint64_t previous=0u;
    for(unsigned i=0u;i<100000u;++i) {
        case_id=i; tick(random_next(&rng)%8192u); accesses=captured=0u;
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==truth && out.raw_tick>=previous);
        previous=out.raw_tick;
        if(registers[FLAG]&1u) interrupt();
        ++sequence_steps;
    }
}
static void documented_aliases(void) {
    phase=7u; hms_avr_clock_sample out={0u,0u,0u};
    for(unsigned missed=2u;missed<=6u;++missed) {
        case_id=missed; ready(((uint64_t)missed<<16)|17u,0u);
        REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_OK && out.raw_tick==65553u);
        REQUIRE(truth-out.raw_tick==((uint64_t)(missed-1u)<<16));
        hms_avr_clock_invalidate(&c); REQUIRE(read_checked(&out)==HMS_AVR_CLOCK_FAULT); ++aliases;
    }
}
int main(int argc,char **argv) {
    if(argc>1 && strcmp(argv[1],"quick")==0) {
        /* Targeted cases retained for mutation checks, not performance shortcuts
         * for the full baseline interleaving/conversion campaigns. */
        phase=1u; case_id=1u;
        for(unsigned p=0u;p<4096u;p+=17u) timeline((UINT64_C(7)<<16)|65535u,7u,p);
        timeline((UINT64_C(8)<<16)|255u,7u,4095u);
        ready((UINT64_C(125)<<16)|250u,125u); hms_avr_clock_sample o={0u,0u,0u};
        REQUIRE(read_checked(&o)==HMS_AVR_CLOCK_OK && o.raw_tick==truth);
    } else { timeline_sweep(); random_timeline(); conversion_sweep(); long_sequences(); }
    lifecycle_and_faults(); late_exhaustion_and_restore(); documented_aliases();
    printf("{\"passed\":true,\"assertions\":%" PRIu64 ",\"timeline_cases\":%" PRIu64
           ",\"conversion_cases\":%" PRIu64 ",\"sequence_steps\":%" PRIu64
           ",\"boundary_cases\":%" PRIu64 ",\"outside_contract_aliases\":%" PRIu64
           ",\"target_executed\":false,\"instruction_emulation\":false}\n",
           assertions,timelines,arithmetic,sequence_steps,boundary_cases,aliases);
    return 0;
}
