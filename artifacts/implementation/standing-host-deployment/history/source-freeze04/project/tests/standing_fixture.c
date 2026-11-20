#include "standing_fixture.h"
#include <string.h>

uint32_t hms_st_fixture_read32(const uint8_t *p){uint8_t i;uint32_t v=0;for(i=0;i<4u;++i)v=(v<<8)|p[i];return v;}
uint64_t hms_st_fixture_read64(const uint8_t *p){uint8_t i;uint64_t v=0;for(i=0;i<8u;++i)v=(v<<8)|p[i];return v;}
void hms_st_fixture_write32(uint8_t *p,uint32_t v){uint8_t i;for(i=0;i<4u;++i){p[3u-i]=(uint8_t)v;v>>=8;}}
void hms_st_fixture_write64(uint8_t *p,uint64_t v){uint8_t i;for(i=0;i<8u;++i){p[7u-i]=(uint8_t)v;v>>=8;}}
static uint16_t read16(const uint8_t *p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint8_t constant(void *user,uint8_t which,uint8_t index){(void)user;return (uint8_t)(0xa0u+(uint8_t)(which*16u)+index);}
static uint8_t clock_sample(void *user,uint64_t *tick,uint16_t *flags){
    uint8_t *d=user;*tick=hms_st_fixture_read64(d+FX_CLOCK);*flags=read16(d+FX_FLAGS);return 1;
}
static uint32_t epoch(void *user,uint8_t channel){return hms_st_fixture_read32((uint8_t *)user+FX_EPOCH+(uint16_t)channel*4u);}
static uint8_t guard(void *user,const uint8_t *configuration,uint8_t initial){
    uint8_t *d=user;uint64_t now=hms_st_fixture_read64(d+FX_CLOCK);
    uint32_t advance=hms_st_fixture_read32(d+FX_GUARD_ADVANCE);
    (void)configuration;
    hms_st_fixture_write64(d+FX_CLOCK,advance<UINT64_MAX-now?now+advance:UINT64_MAX);
    if((d[FX_INJECT]&FX_CLOCK_LOSS)!=0u)d[FX_FLAGS+1]&=(uint8_t)~HMS_EP_CLOCK_QUALIFIED;
    return d[FX_DENY]!=0u || (initial!=0u && d[FX_OUTPUT]!=0u)?HMS_EP_BAD_STATE:HMS_EP_OK;
}
static uint8_t finite_describe(void *user,uint16_t id,const uint8_t *args,uint8_t n,hms_ep_primitive *out){
    (void)user;(void)args;if(id!=1u)return HMS_EP_UNKNOWN_PRIMITIVE;if(n!=0u)return HMS_EP_BAD_ARGUMENT;
    *out=(hms_ep_primitive){1000u,3u,(uint8_t)(1u<<HMS_EP_SIMULATION),1u,0u};return HMS_EP_OK;
}
static uint8_t finite_guard(void *user,uint16_t id,const uint8_t *args,uint8_t n){
    (void)id;(void)n;return guard(user,args,0);
}
static void finite_step(void *user,uint8_t phase,uint16_t id,const uint8_t *args,uint8_t n,
        uint64_t now,const hms_ep_step_limits *limits,hms_ep_report *out){
    uint8_t *d=user;(void)id;(void)args;(void)n;
    if(phase==HMS_EP_START){
        if(now>=limits->ordinary_until || now>=limits->latest_start)return;
        d[FX_FINITE_ACTIVE]=1;d[FX_OUTPUT]=1;hms_st_fixture_write64(d+FX_FINITE_STARTED,now);
        hms_st_fixture_write32(d+FX_DISPATCHES,hms_st_fixture_read32(d+FX_DISPATCHES)+1u);return;
    }
    if(phase==HMS_EP_RUN && now-hms_st_fixture_read64(d+FX_FINITE_STARTED)<2u)return;
    d[FX_FINITE_ACTIVE]=d[FX_OUTPUT]=0;
    if(phase!=HMS_EP_QUIESCENCE_STEP){
        out->terminal_state=phase==HMS_EP_CANCEL_STEP?HMS_EP_CANCELED:(phase==HMS_EP_LOSS_STEP?HMS_EP_FAILED:HMS_EP_COMPLETED);
        if(phase==HMS_EP_CANCEL_STEP)out->cancellation=HMS_EP_CANCEL_ACK;
        out->evidence_kind=HMS_EP_SIMULATION;
    }
    out->quiescent_mask=3;
}
static void sample(uint8_t *d,uint8_t channel,uint64_t now,uint8_t kind,uint8_t *out){
    uint32_t sequence=hms_st_fixture_read32(d+FX_SEQUENCE+(uint16_t)channel*4u);
    uint32_t value=channel==0u?hms_st_fixture_read32(d+FX_DEMAND):hms_st_fixture_read32(d+FX_FEEDBACK);
    if(sequence==UINT32_MAX)return;
    if((d[FX_INJECT]&FX_DUPLICATE)==0u){++sequence;hms_st_fixture_write32(d+FX_SEQUENCE+(uint16_t)channel*4u,sequence);}
    if(channel==1u && value==UINT32_MAX)value=d[FX_OUTPUT]!=0u?1000u:0u;
    out[0]=kind;out[1]=channel;out[2]=(uint8_t)((d[FX_INJECT]&FX_BAD_QUALITY)!=0u?0u:1u);
    out[3]=(d[FX_INJECT]&FX_FALSE_PHYSICAL)!=0u?HMS_EP_PHYSICAL_SENSOR:HMS_EP_SIMULATION;
    out[5]=1;
    hms_st_fixture_write32(out+12,epoch(d,channel)+((d[FX_INJECT]&FX_BAD_EPOCH)!=0u?1u:0u));
    hms_st_fixture_write32(out+16,sequence);hms_st_fixture_write64(out+20,now);hms_st_fixture_write32(out+28,value);
}
static uint8_t boundary(const hms_standing *s,const uint8_t *d,uint8_t phase){
    const hms_endpoint *e=s->endpoint;uint8_t i;
    if(e->standing!=s || e->boot_epoch==0u || s->bytes[ST_SLOT]!=ST_STANDING ||
            s->bytes[ST_OWNED]!=3u || e->operation_length!=134u ||
            (e->flags&(HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_SIMULATOR_ONLY))!=25u)return 0;
    if((read16(d+FX_FLAGS)&(HMS_EP_BOOT_QUALIFIED|HMS_EP_CLOCK_QUALIFIED|HMS_EP_SIMULATOR_ONLY))!=25u ||
            (read16(d+FX_FLAGS)&HMS_EP_PHYSICAL_COMMISSIONED)!=0u || d[FX_DENY]!=0u)return 0;
    for(i=0;i<2u;++i)if(e->fence_floor[i]!=hms_st_fixture_read32(e->operation+80u+(uint16_t)i*4u))return 0;
    if(phase==ST_ACQUIRE_DEMAND || phase==ST_ACQUIRE_FEEDBACK || phase==ST_SET_OUTPUT){
        if((s->bytes[ST_LIFE]!=ST_ACTIVE && s->bytes[ST_LIFE]!=ST_PREPARED) || e->context_valid==0u ||
                e->control_generation!=hms_st_fixture_read32(e->operation+2) || e->context_handle!=read16(e->operation+6) ||
                (read16(d+FX_FLAGS)&HMS_EP_RECONCILE)!=0u)return 0;
    }
    if(phase!=ST_LOSS_OUTPUT){
        for(i=0;i<2u;++i)if(hms_st_fixture_read32(d+FX_EPOCH+(uint16_t)i*4u)!=
                hms_st_fixture_read32(s->bytes+ST_EPOCH+(uint16_t)i*4u))return 0;
    }
    if(phase==ST_SET_OUTPUT){
        uint8_t index=s->bytes[ST_PENDING];
        if(s->bytes[ST_LIFE]!=ST_ACTIVE || e->context_valid==0u || index>=2u ||
                hms_st_fixture_read32(s->arena->record[index])!=hms_st_fixture_read32(s->bytes+ST_ACT) ||
                (s->arena->record[index][40]&7u)!=ST_RECORD_PENDING)return 0;
    }else if(phase==ST_LOSS_OUTPUT && s->bytes[ST_LOSS_COMMAND]!=2u)return 0;
    else if(phase==ST_LOSS_OBSERVE && s->bytes[ST_LOSS_COMMAND]!=3u)return 0;
    return 1;
}
static void standing_step(void *user,const hms_standing *authority,uint8_t phase,uint8_t command,uint64_t now,uint64_t cutoff,uint8_t *out){
    uint8_t *d=user;uint64_t actual=hms_st_fixture_read64(d+FX_CLOCK);
    uint32_t advance=hms_st_fixture_read32(d+FX_STEP_ADVANCE);
    if(actual<now)actual=now;
    actual=advance<UINT64_MAX-actual?actual+advance:UINT64_MAX;
    if((d[FX_INJECT]&FX_LATE)!=0u && cutoff!=UINT64_MAX)actual=cutoff;
    hms_st_fixture_write64(d+FX_CLOCK,actual);
    if((d[FX_INJECT]&FX_CLOCK_LOSS)!=0u)d[FX_FLAGS+1]&=(uint8_t)~HMS_EP_CLOCK_QUALIFIED;
    if(d[FX_BOUNDARY_DRIFT]==1u){
        uint32_t previous=epoch(d,0);
        if(previous!=UINT32_MAX)hms_st_fixture_write32(d+FX_EPOCH,previous+1u);
    }else if(d[FX_BOUNDARY_DRIFT]==2u)d[FX_FLAGS+1]&=(uint8_t)~HMS_EP_CLOCK_QUALIFIED;
    /* Acquisition is potentially effectful bus I/O too. Its sequence cannot
     * advance until the actual installed authority/clock/cutoff gate passes.
     * Revoked-context loss service uses its retained ownership and cleanup
     * envelope; it never restores ordinary authority. */
    if(boundary(authority,d,phase)==0u)return;
    if(actual>=cutoff || cutoff==UINT64_MAX){
        if(phase!=ST_SET_OUTPUT || (d[FX_INJECT]&FX_IGNORE_CUTOFF)==0u)return;
    }
    if(phase==ST_ACQUIRE_DEMAND || phase==ST_ACQUIRE_FEEDBACK){sample(d,phase,actual,ST_REPORT_SAMPLE,out);return;}
    if(phase==ST_LOSS_OBSERVE){
        if((d[FX_INJECT]&FX_NO_QUIET)!=0u || d[FX_OUTPUT]!=0u)return;
        sample(d,1,actual,ST_REPORT_QUIET,out);out[8]=3;
        if(d[FX_WITNESS_TIME]!=0u){
            uint64_t handoff=hms_st_fixture_read64(d+FX_LAST_LOSS_HANDOFF);
            hms_st_fixture_write64(out+20,d[FX_WITNESS_TIME]==1u && handoff!=0u?handoff-1u:handoff);
        }
        return;
    }
    out[0]=ST_REPORT_DISPATCH;out[6]=command;hms_st_fixture_write64(out+20,actual);
    /* Precise actual-boundary refusal is deliberately distinguishable from
     * the injected provider that ignores its cutoff and creates uncertainty. */
    d[FX_OUTPUT]=command;out[7]=7;
    if(phase==ST_SET_OUTPUT)hms_st_fixture_write32(d+FX_DISPATCHES,hms_st_fixture_read32(d+FX_DISPATCHES)+1u);
    else{
        hms_st_fixture_write32(d+FX_LOSSES,hms_st_fixture_read32(d+FX_LOSSES)+1u);
        hms_st_fixture_write64(d+FX_LAST_LOSS_HANDOFF,actual);
        if(d[FX_BOUNDARY_DRIFT]==3u)out[7]=1u; /* Possible loss effect, no confirmed handoff. */
    }
}
void hms_st_fixture_init(hms_st_arena *a,hms_ep_config *finite,hms_st_config *standing){
    memset(a,0,sizeof(*a));a->driver[FX_FLAGS+1]=HMS_EP_BOOT_QUALIFIED|HMS_EP_SIMULATOR_ONLY|HMS_EP_CLOCK_QUALIFIED;
    hms_st_fixture_write32(a->driver+FX_EPOCH,1);hms_st_fixture_write32(a->driver+FX_EPOCH+4,1);
    hms_st_fixture_write32(a->driver+FX_DEMAND,25000);hms_st_fixture_write32(a->driver+FX_FEEDBACK,UINT32_MAX);
    *finite=(hms_ep_config){a->driver,constant,finite_describe,finite_guard,clock_sample,finite_step,60000u,2u};
    *standing=(hms_st_config){a->driver,epoch,guard,standing_step,500u,100u,3u};
}
_Static_assert(sizeof(hms_st_arena)==256u,"Standing arena exceeds original primitive allowance");
