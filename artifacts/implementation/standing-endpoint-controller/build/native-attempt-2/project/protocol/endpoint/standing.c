#include "standing.h"
#include <string.h>

#define ABSENT UINT64_MAX
#define NONE 255u
#define PLATFORM 95u
#define OBS_VALUE 0u
#define OBS_AT 4u
#define OBS_SEQUENCE 12u
#define OBS_EPOCH 16u
#define OBS_QUALITY 20u
#define OBS_CONTINUITY 21u
#define OBS_PENDING 22u
#define WORK_TRANSITION 0u
#define WORK_FEEDBACK_DEADLINE 8u
#define WORK_BASELINE 16u
#define WORK_OUTPUT 20u

static uint16_t r16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0]<<8)|p[1]); }
static uint32_t r32(const uint8_t *p) {
    uint8_t i; uint32_t v=0;
    for(i=0;i<4u;++i) v=(v<<8)|p[i];
    return v;
}
static uint64_t r64(const uint8_t *p) {
    uint8_t i; uint64_t v=0;
    for(i=0;i<8u;++i) v=(v<<8)|p[i];
    return v;
}
/* Avoid implementation-defined unsigned-to-signed conversion. */
static int32_t ri32(const uint8_t *p) {
    uint32_t v=r32(p);
    return v<=INT32_MAX ? (int32_t)v : (int32_t)(-1-(int32_t)(UINT32_MAX-v));
}
static void w16(uint8_t *p,uint16_t v) { p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v; }
static void w32(uint8_t *p,uint32_t v) {
    uint8_t i;for(i=0;i<4u;++i){p[3u-i]=(uint8_t)v;v>>=8;}
}
static void w64(uint8_t *p,uint64_t v) {
    uint8_t i;for(i=0;i<8u;++i){p[7u-i]=(uint8_t)v;v>>=8;}
}
static uint8_t nz(const uint8_t *p,uint8_t n) {
    uint8_t v=0,i;for(i=0;i<n;++i)v|=p[i];return (uint8_t)(v!=0u);
}
static uint16_t flags_of(const hms_standing *s) { return r16(s->bytes+ST_FLAGS); }
static void add_flags(hms_standing *s,uint16_t v) { w16(s->bytes+ST_FLAGS,(uint16_t)(flags_of(s)|v)); }
static uint8_t occupied(const hms_standing *s) { return (uint8_t)(s->bytes[ST_SLOT]==ST_STANDING); }
static uint8_t bump(hms_standing *s) {
    uint32_t v=r32(s->bytes+ST_REV);
    if(v==UINT32_MAX){
        add_flags(s,ST_EXHAUSTED|ST_UNRESOLVED);
        s->bytes[ST_LIFE]=s->bytes[ST_TARGET]=ST_FAULT;
        hms_endpoint_counter_fault(s->endpoint);return 0;
    }
    w32(s->bytes+ST_REV,v+1u);return 1;
}
static uint8_t mode_ok(const hms_standing *s) {
    uint16_t f=s->endpoint->flags;
    return s->endpoint->operation[121]==0u ?
        (uint8_t)((f&HMS_EP_SIMULATOR_ONLY)!=0u && (f&HMS_EP_PHYSICAL_COMMISSIONED)==0u) :
        (uint8_t)((f&HMS_EP_PHYSICAL_COMMISSIONED)!=0u && (f&HMS_EP_SIMULATOR_ONLY)==0u);
}
static uint8_t owns(const hms_standing *s) {
    uint8_t i;const hms_endpoint *e=s->endpoint;
    if(s->bytes[ST_OWNED]!=e->operation[79])return 0;
    for(i=0;i<8u;++i)if((s->bytes[ST_OWNED]&((uint8_t)1u<<i))!=0u &&
            e->fence_floor[i]!=r32(e->operation+80u+(uint16_t)i*4u))return 0;
    return 1;
}
static uint32_t source_epoch(hms_standing *s,uint8_t channel) {
    uint32_t value;
    s->endpoint->callback_active=1;
    value=s->config->source_epoch(s->config->user,channel);
    s->endpoint->callback_active=0;return value;
}
static uint8_t installed_guard(hms_standing *s,const uint8_t *configuration,uint8_t initial) {
    uint8_t value;
    s->endpoint->callback_active=1;
    value=s->config->guard(s->config->user,configuration,initial);
    s->endpoint->callback_active=0;
    return value<=ST_SOURCE_INVALID ? value : HMS_EP_BAD_ARGUMENT;
}
static uint8_t source_bindings(hms_standing *s,const uint8_t *epochs) {
    uint8_t i;
    for(i=0;i<2u;++i)if(source_epoch(s,i)!=r32(epochs+(uint16_t)i*4u))return 0;
    return 1;
}
static uint8_t fresh(const hms_standing *s,uint8_t channel) {
    const uint8_t *o=s->arena->observation[channel];
    uint16_t ready=channel==0u?ST_DEMAND_READY:ST_FEEDBACK_READY;
    uint64_t acquired=r64(o+OBS_AT),now=s->endpoint->now_tick;
    return (uint8_t)((flags_of(s)&ready)!=0u && o[OBS_QUALITY]==1u &&
        o[OBS_CONTINUITY]==1u && r32(o+OBS_EPOCH)==r32(s->bytes+ST_EPOCH+(uint16_t)channel*4u) &&
        acquired!=ABSENT && acquired<=now && now-acquired<r16(s->arena->configuration+18u+(uint16_t)channel*2u));
}
static void cancel_pending(hms_standing *s,uint16_t reason,uint8_t unknown) {
    uint8_t index=s->bytes[ST_PENDING];
    if(index<2u){
        uint8_t *r=s->arena->record[index];
        r[40]=(uint8_t)((r[40]&0xf8u)|(unknown!=0u?ST_RECORD_UNKNOWN:ST_RECORD_INTERRUPTED));
        w16(r+42,reason);s->bytes[ST_PENDING]=NONE;
    }
}
static void loss(hms_standing *s,uint16_t reason,uint8_t target,uint8_t advance) {
    uint8_t changed=0;
    if(occupied(s)==0u)return;
    if((flags_of(s)&ST_LOSS)==0u){
        add_flags(s,ST_LOSS);
        w16(s->bytes+ST_REASON,reason);
        if((s->endpoint->flags&HMS_EP_CLOCK_QUALIFIED)!=0u &&
                s->endpoint->now_tick<ABSENT-s->config->cleanup_ms){
            w64(s->bytes+ST_LOSS_AT,s->endpoint->now_tick);
            w64(s->bytes+ST_CLEANUP,s->endpoint->now_tick+s->config->cleanup_ms);
        }else{
            w64(s->bytes+ST_LOSS_AT,ABSENT);w64(s->bytes+ST_CLEANUP,ABSENT);
        }
        s->bytes[ST_LOSS_COMMAND]=1u;s->bytes[ST_TARGET]=target;
        cancel_pending(s,reason,(uint8_t)((flags_of(s)&ST_UNRESOLVED)!=0u));
        s->bytes[ST_LIFE]=target==ST_FAULT?ST_FAULT:ST_DRAINING;changed=1;
    }else if(target==ST_FAULT && s->bytes[ST_TARGET]!=ST_FAULT){
        s->bytes[ST_TARGET]=s->bytes[ST_LIFE]=ST_FAULT;changed=1;
    }
    if(advance!=0u && changed!=0u)(void)bump(s);
}
static void unknown(hms_standing *s,uint16_t reason) {
    add_flags(s,ST_UNRESOLVED);
    cancel_pending(s,reason,1);
    loss(s,reason,ST_FAULT,1);
    s->bytes[ST_LIFE]=s->bytes[ST_TARGET]=ST_FAULT;
}
static void synchronize(hms_standing *s) {
    hms_endpoint *e=s->endpoint;
    if(occupied(s)==0u)return;
    if((e->flags&HMS_EP_CLOCK_QUALIFIED)==0u){unknown(s,ST_CLOCK);return;}
    if(e->context_valid==0u || e->state==HMS_EP_FAULT ||
            r32(e->operation+2)!=e->control_generation || r16(e->operation+6)!=e->context_handle ||
            hms_endpoint_readiness(e)!=0u || mode_ok(s)==0u || owns(s)==0u){
        loss(s,ST_AUTHORITY,ST_STOPPED,1);return;
    }
    if((s->bytes[ST_LIFE]==ST_ACTIVE || s->bytes[ST_LIFE]==ST_PREPARED) &&
            e->now_tick>=r64(s->bytes+ST_LEASE))loss(s,ST_LEASE_LOSS,ST_SUSPENDED,1);
}
static uint8_t guarded(hms_standing *s,uint8_t require_fresh) {
    uint8_t status=installed_guard(s,s->arena->configuration,0);
    uint8_t epochs=source_bindings(s,s->bytes+ST_EPOCH);
    hms_endpoint_fresh_clock(s->endpoint);synchronize(s);
    if(status!=0u){loss(s,ST_GUARD,ST_STOPPED,1);return status;}
    if(epochs==0u){add_flags(s,ST_DEMAND_FAULT|ST_FEEDBACK_FAULT);loss(s,ST_EPOCH_LOSS,ST_STOPPED,1);return ST_SOURCE_INVALID;}
    status=hms_endpoint_readiness(s->endpoint);if(status!=0u)return status;
    if(s->endpoint->context_valid==0u || mode_ok(s)==0u || owns(s)==0u)return HMS_EP_CONTEXT_MISMATCH;
    if(r32(s->endpoint->operation+2)!=s->endpoint->control_generation ||
            r16(s->endpoint->operation+6)!=s->endpoint->context_handle)return HMS_EP_CONTEXT_MISMATCH;
    if(require_fresh!=0u && (fresh(s,0)==0u || fresh(s,1)==0u))return ST_SOURCE_INVALID;
    return HMS_EP_OK;
}
static uint8_t lease_valid(const hms_standing *s,uint64_t until) {
    return (uint8_t)(until!=ABSENT && until>s->endpoint->now_tick &&
        until-s->endpoint->now_tick<=s->endpoint->config->max_lease_ms);
}
static uint8_t configuration_valid(const uint8_t *c) {
    uint8_t i;
    if(ri32(c)<-100000 || ri32(c+4)>200000 || ri32(c)>=ri32(c+4) ||
            ri32(c+8)<0 || ri32(c+8)>300000 || ri32(c+12)<=0 || ri32(c+12)>100000 ||
            c[28]!=0u || c[29]!=1u || c[30]!=0u || c[31]!=0u)return 0;
    for(i=16;i<=26u;i=(uint8_t)(i+2u)){
        uint16_t v=r16(c+i);
        if(v>60000u || (v==0u && i!=22u && i!=24u))return 0;
    }
    return (uint8_t)(r16(c+16)<r16(c+18) && r16(c+16)<r16(c+20) && r16(c+16)<r16(c+26));
}
uint8_t hms_standing_attach(hms_standing *s,hms_endpoint *e,const hms_st_config *c,hms_st_arena *a) {
    if(s==NULL || e==NULL || c==NULL || a==NULL || e->config==NULL ||
            e->callback_active!=0u || e->standing!=NULL || e->operation_length!=0u ||
            e->call_high_water!=0u || e->receipt.held_mask!=0u || c->source_epoch==NULL ||
            c->guard==NULL || c->step==NULL || c->max_on_ms==0u || c->cleanup_ms==0u ||
            c->cleanup_ms>60000u || c->resource_mask==0u ||
            (uint16_t)c->resource_mask>=((uint16_t)1u<<e->config->resource_count))return 0;
    memset(s,0,sizeof(*s));s->endpoint=e;s->config=c;s->arena=a;
    memset(a->configuration,0,32);memset(a->work,0,24);
    memset(a->observation,0,48);memset(a->record,0,88);
    s->bytes[ST_PENDING]=NONE;e->standing=s;return 1;
}
void hms_standing_finite_slot(hms_standing *s,uint8_t occupied_finite) {
    /* Core calls this only after actual finite commit/retirement. Never clear
     * the independent standing high-water, even while its record is absent. */
    if(s->bytes[ST_SLOT]!=ST_STANDING)s->bytes[ST_SLOT]=occupied_finite!=0u?ST_FINITE:ST_EMPTY;
}
static uint8_t reference(const hms_standing *s,const uint8_t *p) {
    uint32_t n=r32(p+8);
    if(occupied(s)==0u || n!=r32(s->bytes+ST_HIGH))
        return n<=r32(s->bytes+ST_HIGH)?HMS_EP_OLD_OR_FORGOTTEN:HMS_EP_NOT_SEEN;
    return memcmp(s->endpoint->operation+2,p+2,42)==0?HMS_EP_OK:HMS_EP_CONFLICT;
}
static uint8_t open_record(hms_standing *s,const uint8_t *p) {
    hms_endpoint *e=s->endpoint;
    uint8_t i,status;uint32_t number=r32(p+8);
    if(occupied(s)!=0u && number==r32(s->bytes+ST_HIGH))
        return memcmp(e->operation,p,134)==0?HMS_EP_OK:HMS_EP_CONFLICT;
    if(number<=r32(s->bytes+ST_HIGH))return HMS_EP_OLD_OR_FORGOTTEN;
    if(s->bytes[ST_SLOT]!=ST_EMPTY || e->operation_length!=0u || e->receipt.held_mask!=0u)return HMS_EP_BUSY;
    if(e->context_valid==0u || (e->state!=HMS_EP_BOUND && e->state!=HMS_EP_ARMED) ||
            r32(p+2)!=e->control_generation || r16(p+6)!=e->context_handle)return HMS_EP_CONTEXT_MISMATCH;
    status=hms_endpoint_readiness(e);if(status!=0u)return status;
    if(r16(p+44)!=1u)return HMS_EP_UNKNOWN_PRIMITIVE;
    if(p[46]!=32u || configuration_valid(p+47)==0u || nz(p+12,32)==0u ||
            r32(p+122)==0u || r32(p+126)==0u || r32(p+130)==0u)return HMS_EP_BAD_ARGUMENT;
    if(p[120]!=0u || p[121]>1u)return HMS_EP_UNSUPPORTED;
    if((p[121]==0u && (e->flags&HMS_EP_SIMULATOR_ONLY)==0u) ||
            (p[121]==1u && (e->flags&HMS_EP_PHYSICAL_COMMISSIONED)==0u))return HMS_EP_UNCOMMISSIONED;
    if(p[79]!=s->config->resource_mask)return HMS_EP_RESOURCE_MISMATCH;
    for(i=0;i<8u;++i){
        uint32_t f=r32(p+80u+(uint16_t)i*4u);
        if((p[79]&((uint8_t)1u<<i))!=0u){if(f==0u || f<=e->fence_floor[i])return HMS_EP_STALE_FENCE;}
        else if(f!=0u)return HMS_EP_RESERVED;
    }
    status=installed_guard(s,p+47,1);
    if(source_bindings(s,p+126)==0u)status=ST_SOURCE_INVALID;
    hms_endpoint_fresh_clock(e);
    if(status!=0u)return status;
    status=hms_endpoint_readiness(e);if(status!=0u)return status;
    if(e->context_valid==0u || r32(p+2)!=e->control_generation || r16(p+6)!=e->context_handle)return HMS_EP_CONTEXT_MISMATCH;
    if(lease_valid(s,r64(p+112))==0u)return HMS_EP_LEASE_INVALID;
    /* One serialized atomic ownership commit after every check. */
    memset(s->bytes,0,128);w32(s->bytes+ST_HIGH,number);
    s->bytes[ST_SLOT]=ST_STANDING;w32(s->bytes+ST_REV,1);
    memcpy(e->operation,p,134);e->operation_length=134;
    for(i=0;i<8u;++i)if((p[79]&((uint8_t)1u<<i))!=0u)e->fence_floor[i]=r32(p+80u+(uint16_t)i*4u);
    memset(&e->receipt,0,sizeof(e->receipt));
    e->armed_until=0;e->state=HMS_EP_BOUND;e->loss_reason=0;
    memcpy(s->arena->configuration,p+47,32);memset(s->arena->work,0,24);
    memset(s->arena->observation,0,48);memset(s->arena->record,0,88);
    memcpy(s->bytes+ST_EPOCH,p+126,8);w64(s->bytes+ST_LEASE,r64(p+112));
    w64(s->bytes+ST_NEXT,e->now_tick);w64(s->bytes+ST_LOSS_AT,ABSENT);
    w64(s->bytes+ST_CLEANUP,ABSENT);w64(s->bytes+ST_QUIET_AT,ABSENT);
    w64(s->arena->work+WORK_TRANSITION,e->now_tick);
    w64(s->arena->work+WORK_FEEDBACK_DEADLINE,ABSENT);
    s->bytes[ST_LIFE]=ST_PREPARED;s->bytes[ST_OWNED]=p[79];s->bytes[ST_PENDING]=NONE;
    return HMS_EP_OK;
}
static uint8_t ack_valid(const hms_standing *s,uint32_t value) {
    uint32_t old=r32(s->bytes+ST_ACK),high=r32(s->bytes+ST_ACT);
    uint8_t i;
    if(value<old || value>high)return HMS_EP_BAD_ARGUMENT;
    if(high-old!=s->bytes[ST_COUNT] || s->bytes[ST_COUNT]>2u)return HMS_EP_BAD_STATE;
    for(i=0;i<(uint8_t)(value-old);++i){
        const uint8_t *r=s->arena->record[(s->bytes[ST_HEAD]+i)&1u];
        uint8_t state=(uint8_t)(r[40]&7u);
        if(r32(r)!=old+1u+i || (state!=ST_RECORD_SUCCESS && state!=ST_RECORD_FAILED && state!=ST_RECORD_INTERRUPTED) ||
                ((r[40]>>4)&3u)==HMS_EP_DISPUTED)return ST_ACK_PENDING;
        /* Interrupted feedback is not a physical cancellation claim. Keep it
         * locally until the separate loss has a valid aggregate settlement;
         * an unknown loss handoff cannot make this record forgettable. */
        if(state==ST_RECORD_INTERRUPTED &&
                ((flags_of(s)&ST_WITNESS_VALID)==0u ||
                 (flags_of(s)&(ST_UNRESOLVED|ST_DISPUTED))!=0u ||
                 s->bytes[ST_OWNED]==0u || s->bytes[ST_QUIET]!=s->bytes[ST_OWNED] ||
                 (s->bytes[ST_LIFE]!=ST_SUSPENDED && s->bytes[ST_LIFE]!=ST_STOPPED)))return ST_ACK_PENDING;
    }
    return HMS_EP_OK;
}
static void acknowledge(hms_standing *s,uint32_t value) {
    uint8_t n=(uint8_t)(value-r32(s->bytes+ST_ACK));
    while(n!=0u){memset(s->arena->record[s->bytes[ST_HEAD]],0,44);
        s->bytes[ST_HEAD]^=1u;--s->bytes[ST_COUNT];--n;}
    w32(s->bytes+ST_ACK,value);
}
static uint8_t mutation(hms_standing *s,const uint8_t *p) {
    uint8_t status=reference(s,p),op=p[1],life=s->bytes[ST_LIFE];
    uint32_t sequence=r32(p+44),last=r32(s->bytes+ST_MUT);
    if(status!=0u)return status;
    if(sequence==last && last!=0u){
        return memcmp(s->bytes+ST_BODY,p,2)==0 && memcmp(s->bytes+ST_BODY+2,p+48,18)==0?HMS_EP_OK:HMS_EP_CONFLICT;
    }
    if(sequence<=last)return HMS_EP_OLD_OR_FORGOTTEN;
    if(last==UINT32_MAX || r32(s->bytes+ST_REV)==UINT32_MAX){
        add_flags(s,ST_EXHAUSTED);unknown(s,ST_COUNTER);hms_endpoint_counter_fault(s->endpoint);return HMS_EP_COUNTER_EXHAUSTED;
    }
    if(sequence!=last+1u)return HMS_EP_BAD_ARGUMENT;
    if(r32(p+48)!=r32(s->bytes+ST_REV))return ST_BAD_REVISION;
    switch(op){
    case ST_START:
        if(life!=ST_PREPARED)return HMS_EP_BAD_STATE;
        status=guarded(s,1);if(status!=0u)return status;
        if(s->bytes[ST_LIFE]!=ST_PREPARED)return HMS_EP_BAD_STATE;
        if(ri32(s->arena->observation[1])!=0 || s->arena->work[WORK_OUTPUT]!=0u)return ST_SOURCE_INVALID;
        break;
    case ST_RENEW:
        if(life!=ST_ACTIVE)return HMS_EP_BAD_STATE;
        status=guarded(s,1);if(status!=0u)return status;
        if(s->bytes[ST_LIFE]!=ST_ACTIVE || lease_valid(s,r64(p+52))==0u || r64(p+52)<=r64(s->bytes+ST_LEASE))return HMS_EP_LEASE_INVALID;
        break;
    case ST_ACKNOWLEDGE:
        status=ack_valid(s,r32(p+60));if(status!=0u)return status;
        break;
    case ST_SUSPEND_OP:
        if(life!=ST_ACTIVE && life!=ST_PREPARED)return HMS_EP_BAD_STATE;
        break;
    case ST_RESUME:
        if(life!=ST_SUSPENDED || (flags_of(s)&(ST_UNRESOLVED|ST_DISPUTED))!=0u ||
                s->bytes[ST_QUIET]!=s->bytes[ST_OWNED] || (flags_of(s)&ST_WITNESS_VALID)==0u ||
                r32(s->bytes+ST_ACK)!=r32(s->bytes+ST_ACT) || s->bytes[ST_COUNT]!=0u)return HMS_EP_BAD_STATE;
        if(r16(s->bytes+ST_REASON)!=ST_SUSPEND && r16(s->bytes+ST_REASON)!=ST_LEASE_LOSS && r16(s->bytes+ST_REASON)!=ST_LEDGER)return HMS_EP_BAD_STATE;
        status=guarded(s,0);if(status!=0u)return status;
        if(lease_valid(s,r64(p+52))==0u)return HMS_EP_LEASE_INVALID;
        break;
    case ST_STOP_OP: break;
    case ST_RETIRE:
        if(life!=ST_STOPPED || s->bytes[ST_QUIET]!=s->bytes[ST_OWNED] ||
                (flags_of(s)&(ST_UNRESOLVED|ST_DISPUTED))!=0u ||
                r32(p+60)!=r32(s->bytes+ST_ACT))return HMS_EP_BUSY;
        status=ack_valid(s,r32(p+60));if(status!=0u)return status;
        break;
    default:return HMS_EP_UNSUPPORTED;
    }
    /* Guard/clock callbacks may have advanced the asynchronous revision. */
    if(r32(p+48)!=r32(s->bytes+ST_REV))return ST_BAD_REVISION;
    memcpy(s->bytes+ST_BODY,p,2);memcpy(s->bytes+ST_BODY+2,p+48,18);
    w32(s->bytes+ST_MUT,sequence);if(bump(s)==0u)return HMS_EP_COUNTER_EXHAUSTED;
    switch(op){
    case ST_START:s->bytes[ST_LIFE]=ST_ACTIVE;add_flags(s,ST_STARTED);break;
    case ST_RENEW:w64(s->bytes+ST_LEASE,r64(p+52));break;
    case ST_ACKNOWLEDGE:acknowledge(s,r32(p+60));break;
    case ST_SUSPEND_OP:loss(s,ST_SUSPEND,ST_SUSPENDED,0);break;
    case ST_RESUME:{
        uint16_t keep=(uint16_t)(flags_of(s)&(ST_EVER|ST_STARTED));
        s->arena->work[WORK_OUTPUT]=s->bytes[ST_WITNESS+20];
        w64(s->arena->work+WORK_TRANSITION,r64(s->bytes+ST_QUIET_AT));
        w64(s->arena->work+WORK_FEEDBACK_DEADLINE,ABSENT);
        /* Exported loss evidence advances source continuity too. Move that
         * accepted watermark before clearing the witness, so the next sample
         * is compared with its actual predecessor rather than pre-loss data. */
        memcpy(s->arena->observation[1],s->bytes+ST_WITNESS+16,4);
        memcpy(s->arena->observation[1]+OBS_AT,s->bytes+ST_WITNESS+8,8);
        memcpy(s->arena->observation[1]+OBS_SEQUENCE,s->bytes+ST_WITNESS+4,4);
        s->arena->observation[0][OBS_PENDING]=s->arena->observation[1][OBS_PENDING]=0;
        w16(s->bytes+ST_FLAGS,(uint16_t)(keep|ST_RESUMED));
        w64(s->bytes+ST_LEASE,r64(p+52));w64(s->bytes+ST_NEXT,s->endpoint->now_tick);
        w64(s->bytes+ST_LOSS_AT,ABSENT);w64(s->bytes+ST_CLEANUP,ABSENT);w64(s->bytes+ST_QUIET_AT,ABSENT);
        memset(s->bytes+ST_WITNESS,0,22);w16(s->bytes+ST_REASON,0);
        s->bytes[ST_QUIET]=s->bytes[ST_LOSS_COMMAND]=s->bytes[ST_PHASE]=s->bytes[ST_TARGET]=0;
        s->bytes[ST_LIFE]=ST_PREPARED;break;
    }
    case ST_STOP_OP:
        if(s->bytes[ST_LIFE]==ST_SUSPENDED){s->bytes[ST_TARGET]=s->bytes[ST_LIFE]=ST_STOPPED;}
        else if(s->bytes[ST_LIFE]!=ST_STOPPED && s->bytes[ST_LIFE]!=ST_FAULT){
            loss(s,ST_STOP,ST_STOPPED,0);s->bytes[ST_TARGET]=ST_STOPPED;
        }
        break;
    case ST_RETIRE:{
        uint32_t high=r32(s->bytes+ST_HIGH);
        acknowledge(s,r32(p+60));memset(s->bytes,0,128);w32(s->bytes+ST_HIGH,high);s->bytes[ST_PENDING]=NONE;
        s->endpoint->operation_length=0;memset(s->endpoint->operation,0,192);
        memset(&s->endpoint->receipt,0,sizeof(s->endpoint->receipt));s->endpoint->loss_reason=0;
        hms_endpoint_refresh(s->endpoint,s->endpoint->now_tick,(uint16_t)(s->endpoint->flags&PLATFORM));break;
    }
    default:break;
    }
    return HMS_EP_OK;
}

static uint8_t known(uint8_t op) {
    return (uint8_t)(op==ST_DESCRIBE || op==ST_BIND || op==ST_REVOKE ||
        (op>=ST_OPEN && op<=ST_RETIRE));
}
static uint8_t syntax(const uint8_t *p,uint16_t n) {
    uint8_t op=p[1];uint16_t expected=66;
    if(p[0]!=2u)return HMS_EP_UNSUPPORTED;
    if(op==ST_DESCRIBE)expected=3;
    else if(op==ST_BIND)expected=72;
    else if(op==ST_REVOKE)expected=10;
    else if(op==ST_OPEN)expected=134;
    else if(op==ST_STATUS)expected=49;
    if(n!=expected)return HMS_EP_BAD_LENGTH;
    if(op==ST_DESCRIBE)return p[2]<=1u?HMS_EP_OK:ST_BAD_PAGE;
    if(r32(p+2)==0u || r16(p+6)==0u)return HMS_EP_BAD_ARGUMENT;
    if(op<ST_OPEN)return HMS_EP_OK;
    if(r32(p+8)==0u || nz(p+12,32)==0u)return HMS_EP_BAD_ARGUMENT;
    if(op==ST_OPEN)return HMS_EP_OK;
    if(op==ST_STATUS){
        if(p[44]>2u)return ST_BAD_PAGE;
        if((p[44]!=2u && r32(p+45)!=0u) || (p[44]==2u && r32(p+45)==0u))return HMS_EP_RESERVED;
        return HMS_EP_OK;
    }
    if(r32(p+44)==0u || r32(p+48)==0u)return HMS_EP_BAD_ARGUMENT;
    if(op!=ST_RENEW && op!=ST_RESUME && r64(p+52)!=0u)return HMS_EP_RESERVED;
    if(op!=ST_ACKNOWLEDGE && op!=ST_RETIRE && r32(p+60)!=0u)return HMS_EP_RESERVED;
    if((op==ST_SUSPEND_OP && r16(p+64)!=ST_SUSPEND) ||
            (op==ST_STOP_OP && r16(p+64)!=ST_STOP) ||
            (op!=ST_SUSPEND_OP && op!=ST_STOP_OP && r16(p+64)!=0u))return HMS_EP_RESERVED;
    return HMS_EP_OK;
}
static void header(hms_standing *s,const uint8_t *request,uint16_t n,
        uint32_t sequence,uint8_t status,uint8_t page,uint8_t *out) {
    memset(out,0,66);out[0]=2;out[1]=(uint8_t)(request[1]|0x80u);
    w32(out+2,sequence);out[6]=status;out[7]=page;
    if(occupied(s)!=0u){
        memcpy(out+8,s->endpoint->operation+2,42);
        memcpy(out+50,s->bytes+ST_REV,8);memcpy(out+58,s->bytes+ST_ACT,8);
    }else if(n>=44u && request[1]>=ST_OPEN){memcpy(out+8,request+2,42);}
}
static void constants(hms_endpoint *e,uint8_t which,uint8_t *p,uint8_t n) {
    uint8_t i;e->callback_active=1;
    for(i=0;i<n;++i)p[i]=e->config->constant_byte(e->config->user,which,i);
    e->callback_active=0;
}
static uint16_t describe(hms_standing *s,uint8_t page,uint8_t *out) {
    hms_endpoint *e=s->endpoint;uint8_t i;
    if(page==0u){
        constants(e,HMS_EP_INCARNATION,out,16);constants(e,HMS_EP_FIRMWARE,out+16,32);
        constants(e,HMS_EP_MANIFEST,out+48,32);return 80;
    }
    w32(out,e->control_generation);w16(out+4,e->context_handle);
    memcpy(out+6,e->context_digest,32);w64(out+38,e->now_tick);
    w16(out+46,e->flags);out[48]=e->state;out[49]=e->config->resource_count;
    out[50]=s->bytes[ST_SLOT];out[51]=s->config->resource_mask;w16(out+52,1);
    out[54]=2;out[55]=2;out[56]=32;out[57]=1;
    w32(out+58,e->config->max_lease_ms);w32(out+62,s->config->max_on_ms);
    w16(out+66,s->config->cleanup_ms);
    w32(out+68,source_epoch(s,0));w32(out+72,source_epoch(s,1));
    w32(out+76,r32(s->bytes+ST_HIGH));w32(out+80,e->call_high_water);
    for(i=0;i<8u;++i)w32(out+84u+(uint16_t)i*4u,e->fence_floor[i]);
    return 116;
}
static uint8_t find_record(const hms_standing *s,uint32_t cursor,uint8_t *index) {
    uint8_t i;
    if(cursor<=r32(s->bytes+ST_ACK))return HMS_EP_OLD_OR_FORGOTTEN;
    if(cursor>r32(s->bytes+ST_ACT))return HMS_EP_NOT_SEEN;
    for(i=0;i<s->bytes[ST_COUNT] && i<2u;++i){
        uint8_t slot=(uint8_t)((s->bytes[ST_HEAD]+i)&1u);
        if(r32(s->arena->record[slot])==cursor){*index=slot;return HMS_EP_OK;}
    }
    return HMS_EP_BAD_STATE;
}
uint8_t hms_standing_handle(hms_standing *s,uint8_t kind,uint8_t channel,
        uint64_t session,uint32_t sequence,const uint8_t *p,uint16_t n,
        uint64_t now,uint16_t platform,uint8_t *out,uint16_t *out_length) {
    uint8_t status,page=0,index=0,descriptor=0,op;
    hms_endpoint *e;
    if(out_length!=NULL)*out_length=0;
    if(s==NULL || s->endpoint==NULL || p==NULL || n<2u || n>192u || known(p[1])==0u)return 0;
    e=s->endpoint;if(e->callback_active!=0u || e->standing!=s)return 0;
    op=p[1];hms_endpoint_refresh(e,now,platform);synchronize(s);
    status=syntax(p,n);
    if(status==0u && (kind!=1u || channel!=0u))status=HMS_EP_UNSUPPORTED;
    if(status==0u && op==ST_DESCRIBE && session!=0u)status=HMS_EP_BOOT_MISMATCH;
    if(status==0u && op!=ST_DESCRIBE){
        if((e->flags&HMS_EP_BOOT_QUALIFIED)==0u)status=HMS_EP_BOOT_UNQUALIFIED;
        else if(session!=e->boot_epoch)status=HMS_EP_BOOT_MISMATCH;
        else if(sequence==0u)status=HMS_EP_BAD_ARGUMENT;
    }
    if(e->response_sequence==UINT32_MAX){
        hms_endpoint_counter_fault(e);synchronize(s);
        if(op!=ST_STOP_OP && op!=ST_SUSPEND_OP && op!=ST_REVOKE)return 0;
    }
    if(status==0u){
        switch(op){
        case ST_DESCRIBE:page=p[2];descriptor=1;break;
        case ST_BIND:status=hms_endpoint_bind_shared(e,p);page=1;descriptor=1;break;
        case ST_REVOKE:
            status=hms_endpoint_revoke_shared(e,p);synchronize(s);
            if(occupied(s)==0u){page=1;descriptor=1;}break;
        case ST_OPEN:status=open_record(s,p);break;
        case ST_STATUS:
            status=reference(s,p);page=p[44];
            if(status==0u && page==2u)status=find_record(s,r32(p+45),&index);
            break;
        default:status=mutation(s,p);if(op==ST_RETIRE)page=NONE;break;
        }
    }
    hms_endpoint_refresh(e,e->now_tick,(uint16_t)(e->flags&PLATFORM));synchronize(s);
    if(e->response_sequence==UINT32_MAX)return 0;
    ++e->response_sequence;
    if(out==NULL)return 1;
    if(status!=0u)page=NONE;
    header(s,p,n,sequence,status,page,out);
    if(out_length!=NULL){
        *out_length=66;
        if(status==0u && page!=NONE){
            if(descriptor!=0u)*out_length=(uint16_t)(66u+describe(s,page,out+66));
            else if(page==0u){
                memcpy(out+66,s->bytes+4,124);
                /* Before a witness exists this storage may hold the private
                 * loss-handoff timestamp; never publish it as quiescence. */
                if((flags_of(s)&ST_WITNESS_VALID)==0u)w64(out+135,ABSENT);
                *out_length=190;
            }
            else if(page==1u){memcpy(out+66,s->arena->observation,48);*out_length=114;}
            else{memcpy(out+66,s->arena->record[index],44);*out_length=110;}
        }
    }
    return 1;
}

static uint8_t evidence_ok(const hms_standing *s,const uint8_t *r) {
    if(s->endpoint->operation[121]==0u)
        return (uint8_t)(r[3]==HMS_EP_SIMULATION && r[4]==HMS_EP_UNVERIFIED);
    return (uint8_t)(r[3]==HMS_EP_PHYSICAL_SENSOR && r[4]==HMS_EP_VERIFIED);
}
static uint8_t report_reserved(const uint8_t *r) {
    return (uint8_t)(r[9]==0u && r[10]==0u && r[11]==0u && r[6]<=1u && (r[7]&0xf8u)==0u);
}
static void driver(hms_standing *s,uint8_t phase,uint8_t command,uint64_t cutoff,uint8_t *report) {
    memset(report,0,32);s->endpoint->callback_active=1;
    s->config->step(s->config->user,s,phase,command,s->endpoint->now_tick,cutoff,report);
    s->endpoint->callback_active=0;
    hms_endpoint_fresh_clock(s->endpoint);synchronize(s);
    if((phase==ST_ACQUIRE_DEMAND || phase==ST_ACQUIRE_FEEDBACK || phase==ST_SET_OUTPUT) &&
            (flags_of(s)&ST_LOSS)==0u && source_bindings(s,s->bytes+ST_EPOCH)==0u){
        add_flags(s,ST_DEMAND_FAULT|ST_FEEDBACK_FAULT);loss(s,ST_EPOCH_LOSS,ST_STOPPED,1);
    }
    if(report[4]==HMS_EP_DISPUTED){
        uint8_t pending=s->bytes[ST_PENDING];add_flags(s,ST_DISPUTED);
        if(pending<2u)s->arena->record[pending][40]|=(uint8_t)(HMS_EP_DISPUTED<<4);
        unknown(s,ST_DRIVER);
    }
}
static void input_fault(hms_standing *s,uint8_t channel,uint16_t reason) {
    add_flags(s,channel==0u?ST_DEMAND_FAULT:ST_FEEDBACK_FAULT);
    loss(s,reason,ST_STOPPED,1);
}
static void accept_observation(hms_standing *s,uint8_t channel,const uint8_t *r) {
    uint8_t *o=s->arena->observation[channel];
    uint32_t sequence=r32(r+16),old=r32(o+OBS_SEQUENCE);
    uint64_t acquired=r64(r+20);int32_t value=ri32(r+28);
    if(r[0]==ST_REPORT_NONE)return;
    if(r[0]!=ST_REPORT_SAMPLE || r[1]!=channel || report_reserved(r)==0u || r[6]!=0u || r[7]!=0u || r[8]!=0u ||
            r[2]!=1u || r[5]!=1u || evidence_ok(s,r)==0u){input_fault(s,channel,ST_QUALITY);return;}
    if(r32(r+12)!=r32(s->bytes+ST_EPOCH+(uint16_t)channel*4u)){
        input_fault(s,channel,ST_EPOCH_LOSS);return;
    }
    if(sequence==0u || sequence<old || (old!=0u && sequence>old && (old==UINT32_MAX || sequence!=old+1u))){
        input_fault(s,channel,ST_GAP);return;
    }
    if(acquired==ABSENT || acquired>s->endpoint->now_tick ||
            (old!=0u && acquired<r64(o+OBS_AT)) ||
            s->endpoint->now_tick-acquired>=r16(s->arena->configuration+18u+(uint16_t)channel*2u)){
        input_fault(s,channel,ST_STALE);return;
    }
    if((channel==0u && (value<-100000 || value>200000)) ||
            (channel==1u && (value<0 || value>100000))){input_fault(s,channel,ST_QUALITY);return;}
    if(sequence==old){
        if(ri32(o)!=value || r64(o+OBS_AT)!=acquired || r32(o+OBS_EPOCH)!=r32(r+12))input_fault(s,channel,ST_GAP);
        return;
    }
    memcpy(o,r+28,4);memcpy(o+OBS_AT,r+20,8);memcpy(o+OBS_SEQUENCE,r+16,4);
    memcpy(o+OBS_EPOCH,r+12,4);o[OBS_QUALITY]=1;o[OBS_CONTINUITY]=1;o[OBS_PENDING]=1;o[23]=0;
    add_flags(s,channel==0u?ST_DEMAND_READY:ST_FEEDBACK_READY);
}
static uint8_t account_ok(hms_standing *s,uint8_t commit,uint64_t until) {
    uint64_t total=r32(s->bytes+ST_ACCOUNT),start=r64(s->arena->work+WORK_TRANSITION);
    if(s->arena->work[WORK_OUTPUT]!=0u){
        if(start==ABSENT || until<start || until-start>UINT32_MAX-total)return 0;
        total+=until-start;
    }
    if(commit!=0u)w32(s->bytes+ST_ACCOUNT,(uint32_t)total);
    return (uint8_t)(total<s->config->max_on_ms);
}
static void feedback(hms_standing *s) {
    uint8_t slot=s->bytes[ST_PENDING],success=0;
    uint8_t *r,*o;
    if(slot>=2u)return;
    r=s->arena->record[slot];o=s->arena->observation[1];
    if(fresh(s,1)!=0u && r64(o+OBS_AT)>r64(r+4) && r32(o+OBS_SEQUENCE)>r32(r+22) && o[OBS_PENDING]!=0u){
        if(r[39]==0u)success=(uint8_t)(ri32(o)==0);
        else if(ri32(o)>=ri32(s->arena->configuration+12)){
            int64_t improvement=(int64_t)ri32(s->arena->work+WORK_BASELINE)-(int64_t)ri32(s->arena->observation[0]);
            success=(uint8_t)(ri32(s->arena->configuration+8)==0 ||
                (fresh(s,0)!=0u && r64(s->arena->observation[0]+OBS_AT)>r64(r+4) &&
                 r32(s->arena->observation[0]+OBS_SEQUENCE)>r32(r+12) && improvement>=ri32(s->arena->configuration+8)));
        }
        memcpy(r+22,o+OBS_SEQUENCE,4);memcpy(r+26,o+OBS_AT,8);memcpy(r+34,o,4);
        r[41]=(uint8_t)((s->endpoint->operation[121]==0u?HMS_EP_SIMULATION:HMS_EP_PHYSICAL_SENSOR)|8u);
        o[OBS_PENDING]=0;
    }
    if(s->endpoint->now_tick>=r64(s->arena->work+WORK_FEEDBACK_DEADLINE))success=0;
    if(success!=0u){
        r[40]=(uint8_t)(ST_RECORD_SUCCESS|8u|(s->endpoint->operation[121]!=0u?(HMS_EP_VERIFIED<<4):0u));
        s->bytes[ST_PENDING]=NONE;
    }else if(s->endpoint->now_tick>=r64(s->arena->work+WORK_FEEDBACK_DEADLINE)){
        r[40]=(uint8_t)(ST_RECORD_FAILED|8u);w16(r+42,ST_FEEDBACK);s->bytes[ST_PENDING]=NONE;
        loss(s,ST_FEEDBACK,ST_STOPPED,1);
    }
}
static uint8_t dispatch_report(const uint8_t *r,uint8_t wanted,uint64_t before,uint64_t after,uint64_t cutoff) {
    return (uint8_t)(report_reserved(r)!=0u && r[0]==ST_REPORT_DISPATCH &&
        r[1]==0u && r[2]==0u && r[3]==0u && r[4]==0u && r[5]==0u && r[6]==wanted &&
        r[7]==7u && r[8]==0u && r32(r+12)==0u && r32(r+16)==0u && r32(r+28)==0u &&
        r64(r+20)>=before && r64(r+20)<=after && r64(r+20)<cutoff);
}
static uint64_t dispatch_cutoff(const hms_standing *s) {
    uint8_t i;uint64_t cutoff=r64(s->bytes+ST_LEASE),at,candidate;
    uint16_t window=r16(s->arena->configuration+26);
    if(cutoff<=window)return 0;
    /* Actual handoff plus the complete response window must fit the lease. */
    cutoff=cutoff-window+1u;
    for(i=0;i<2u;++i){
        uint16_t age=r16(s->arena->configuration+18u+(uint16_t)i*2u);
        at=r64(s->arena->observation[i]+OBS_AT);
        candidate=at<ABSENT-age?at+age:ABSENT;
        if(candidate<cutoff)cutoff=candidate;
    }
    if(s->arena->work[WORK_OUTPUT]!=0u){
        uint32_t used=r32(s->bytes+ST_ACCOUNT),left;
        if(used>=s->config->max_on_ms)return 0;
        left=s->config->max_on_ms-used;at=r64(s->arena->work+WORK_TRANSITION);
        candidate=at<ABSENT-left?at+left:ABSENT;
        if(candidate<cutoff)cutoff=candidate;
    }
    return cutoff;
}
static void transition(hms_standing *s,uint8_t wanted,uint8_t *report) {
    uint8_t index,*r,status;uint64_t before,cutoff;
    uint32_t high=r32(s->bytes+ST_ACT);
    if(s->bytes[ST_COUNT]>=2u){loss(s,ST_LEDGER,ST_SUSPENDED,1);return;}
    if(high==UINT32_MAX || high>=r32(s->endpoint->operation+122)){
        add_flags(s,ST_EXHAUSTED);loss(s,ST_COUNTER,ST_STOPPED,1);return;
    }
    status=guarded(s,1);
    if(status!=0u || s->bytes[ST_LIFE]!=ST_ACTIVE){
        loss(s,status==ST_SOURCE_INVALID?ST_EPOCH_LOSS:ST_GUARD,ST_STOPPED,1);return;
    }
    if(account_ok(s,0,s->endpoint->now_tick)==0u){loss(s,ST_ACCOUNT_LOSS,ST_STOPPED,1);return;}
    before=s->endpoint->now_tick;
    cutoff=dispatch_cutoff(s);
    if(before>=cutoff){loss(s,ST_TIMING,ST_STOPPED,1);return;}
    if(before>=ABSENT-r16(s->arena->configuration+26)){unknown(s,ST_COUNTER);return;}
    index=(uint8_t)((s->bytes[ST_HEAD]+s->bytes[ST_COUNT])&1u);r=s->arena->record[index];
    memset(r,0,44);w32(r,high+1u);w64(r+4,before);
    memcpy(r+12,s->arena->observation[0]+OBS_SEQUENCE,4);memcpy(r+16,s->arena->observation[0],4);
    w16(r+20,(uint16_t)(before-r64(s->arena->observation[0]+OBS_AT)));
    memcpy(r+22,s->arena->observation[1]+OBS_SEQUENCE,4);w64(r+26,ABSENT);
    r[38]=s->arena->work[WORK_OUTPUT];r[39]=wanted;r[40]=ST_RECORD_PENDING|8u;
    w32(s->bytes+ST_ACT,high+1u);++s->bytes[ST_COUNT];s->bytes[ST_PENDING]=index;add_flags(s,ST_EVER);
    /* Identity and possible-effect record exist before entering the driver. */
    driver(s,ST_SET_OUTPUT,wanted,cutoff,report);
    if(s->bytes[ST_LIFE]!=ST_ACTIVE || (s->endpoint->flags&HMS_EP_CLOCK_QUALIFIED)==0u ||
            s->endpoint->now_tick>=cutoff || dispatch_report(report,wanted,before,s->endpoint->now_tick,cutoff)==0u){
        r[40]=(uint8_t)((r[40]&0xf8u)|ST_RECORD_UNKNOWN);w16(r+42,ST_DRIVER);unknown(s,ST_DRIVER);return;
    }
    if(account_ok(s,1,r64(report+20))==0u){unknown(s,ST_ACCOUNT_LOSS);return;}
    /* Actual dispatch time can be later than pre-call time. Preserve exact
     * demand age relative to it, refusing overflow/freshness loss. */
    if(r64(report+20)-r64(s->arena->observation[0]+OBS_AT)>=r16(s->arena->configuration+18)){
        unknown(s,ST_TIMING);return;
    }
    w64(r+4,r64(report+20));w16(r+20,(uint16_t)(r64(report+20)-r64(s->arena->observation[0]+OBS_AT)));
    w64(s->arena->work+WORK_TRANSITION,r64(report+20));s->arena->work[WORK_OUTPUT]=wanted;
    memcpy(s->arena->work+WORK_BASELINE,s->arena->observation[0],4);
    w64(s->arena->work+WORK_FEEDBACK_DEADLINE,r64(report+20)+r16(s->arena->configuration+26));
}
static void evaluate(hms_standing *s,uint8_t *report) {
    uint8_t wanted=s->arena->work[WORK_OUTPUT];
    uint64_t elapsed;
    if(s->bytes[ST_LIFE]!=ST_ACTIVE || s->bytes[ST_PENDING]!=NONE || s->arena->observation[0][OBS_PENDING]==0u)return;
    s->arena->observation[0][OBS_PENDING]=0;
    if(fresh(s,0)==0u || fresh(s,1)==0u){loss(s,ST_STALE,ST_STOPPED,1);return;}
    if(ri32(s->arena->observation[0])>=ri32(s->arena->configuration+4))wanted=1;
    else if(ri32(s->arena->observation[0])<=ri32(s->arena->configuration))wanted=0;
    if(wanted==s->arena->work[WORK_OUTPUT])return;
    if(s->endpoint->now_tick<r64(s->arena->work+WORK_TRANSITION)){unknown(s,ST_CLOCK);return;}
    elapsed=s->endpoint->now_tick-r64(s->arena->work+WORK_TRANSITION);
    if(elapsed<r16(s->arena->configuration+(wanted==0u?22u:24u)))return;
    transition(s,wanted,report);
}
static void loss_service(hms_standing *s,uint8_t *report) {
    uint64_t before=s->endpoint->now_tick,cutoff=r64(s->bytes+ST_CLEANUP);
    uint8_t state=s->bytes[ST_LOSS_COMMAND];
    if(s->bytes[ST_QUIET]==s->bytes[ST_OWNED] || state==4u)return;
    if(cutoff!=ABSENT && before>=cutoff){unknown(s,ST_TIMING);s->bytes[ST_LOSS_COMMAND]=4;return;}
    if(state==1u){
        s->bytes[ST_LOSS_COMMAND]=2;add_flags(s,ST_LOSS_POSSIBLE);
        driver(s,ST_LOSS_OUTPUT,0,cutoff,report);
        if((s->endpoint->flags&HMS_EP_CLOCK_QUALIFIED)==0u || cutoff==ABSENT ||
                s->endpoint->now_tick>=cutoff || dispatch_report(report,0,before,s->endpoint->now_tick,cutoff)==0u){
            unknown(s,ST_DRIVER);s->bytes[ST_LOSS_COMMAND]=4;return;
        }
        /* Temporary lifetime-disjoint reuse: while state3 and !WITNESS_VALID,
         * QUIET_AT is the precise loss-handoff tick, not quiescence evidence.
         * The wire encoder still emits ABSENT. First-loss time is untouched. */
        w64(s->bytes+ST_QUIET_AT,r64(report+20));s->bytes[ST_LOSS_COMMAND]=3;return;
    }
    if(state!=3u)return;
    driver(s,ST_LOSS_OBSERVE,0,cutoff,report);
    if((s->endpoint->flags&HMS_EP_CLOCK_QUALIFIED)==0u){s->bytes[ST_LOSS_COMMAND]=4;return;}
    if(cutoff==ABSENT || s->endpoint->now_tick>=cutoff){unknown(s,ST_TIMING);s->bytes[ST_LOSS_COMMAND]=4;return;}
    if(report[0]==ST_REPORT_NONE)return;
    if((s->endpoint->flags&HMS_EP_CLOCK_QUALIFIED)==0u || cutoff==ABSENT ||
            s->endpoint->now_tick>=cutoff || report_reserved(report)==0u ||
            report[0]!=ST_REPORT_QUIET || report[1]!=1u || report[2]!=1u || report[5]!=1u ||
            evidence_ok(s,report)==0u || report[6]!=0u || report[7]!=0u ||
            report[8]!=s->bytes[ST_OWNED] || r32(report+12)!=r32(s->bytes+ST_EPOCH+4) ||
            r32(report+16)<=r32(s->arena->observation[1]+OBS_SEQUENCE) ||
            r64(s->bytes+ST_QUIET_AT)==ABSENT || r64(report+20)<=r64(s->bytes+ST_QUIET_AT) ||
            r64(report+20)>s->endpoint->now_tick ||
            s->endpoint->now_tick-r64(report+20)>=r16(s->arena->configuration+20) || ri32(report+28)!=0){
        unknown(s,ST_DRIVER);s->bytes[ST_LOSS_COMMAND]=4;return;
    }
    s->bytes[ST_WITNESS]=1;s->bytes[ST_WITNESS+1]=1;
    s->bytes[ST_WITNESS+2]=report[3];s->bytes[ST_WITNESS+3]=report[4];
    memcpy(s->bytes+ST_WITNESS+4,report+16,4);memcpy(s->bytes+ST_WITNESS+8,report+20,8);
    memcpy(s->bytes+ST_WITNESS+16,report+28,4);s->bytes[ST_WITNESS+20]=0;s->bytes[ST_WITNESS+21]=0;
    /* Conservation is charged through confirmed quiescence, an explicit upper
     * bound when the loss command took effect before this observation. */
    if(s->arena->work[WORK_OUTPUT]!=0u){
        uint64_t duration=s->endpoint->now_tick-r64(s->arena->work+WORK_TRANSITION);
        if(s->endpoint->now_tick<r64(s->arena->work+WORK_TRANSITION) ||
                duration>UINT32_MAX-r32(s->bytes+ST_ACCOUNT)){unknown(s,ST_COUNTER);return;}
        w32(s->bytes+ST_ACCOUNT,r32(s->bytes+ST_ACCOUNT)+(uint32_t)duration);
    }
    add_flags(s,ST_WITNESS_VALID);s->bytes[ST_QUIET]=s->bytes[ST_OWNED];
    w64(s->bytes+ST_QUIET_AT,s->endpoint->now_tick);
    s->bytes[ST_LIFE]=s->bytes[ST_TARGET];(void)bump(s);
}
void hms_standing_poll(hms_standing *s) {
    uint8_t report[32],phase,status;
    if(s==NULL || s->endpoint==NULL || s->endpoint->standing!=s || s->endpoint->callback_active!=0u || occupied(s)==0u)return;
    synchronize(s);
    if((flags_of(s)&ST_LOSS)!=0u){loss_service(s,report);return;}
    if(r32(s->bytes+ST_MUT)==UINT32_MAX || r32(s->bytes+ST_REV)==UINT32_MAX){
        add_flags(s,ST_EXHAUSTED);loss(s,ST_COUNTER,ST_STOPPED,1);return;
    }
    if(s->bytes[ST_LIFE]!=ST_PREPARED && s->bytes[ST_LIFE]!=ST_ACTIVE)return;
    status=guarded(s,0);
    if(status!=0u || (flags_of(s)&ST_LOSS)!=0u){
        if((flags_of(s)&ST_LOSS)==0u)loss(s,status==ST_SOURCE_INVALID?ST_EPOCH_LOSS:ST_GUARD,ST_STOPPED,1);
        return;
    }
    if(s->bytes[ST_LIFE]==ST_ACTIVE){
        if(fresh(s,0)==0u || fresh(s,1)==0u){loss(s,ST_STALE,ST_STOPPED,1);return;}
        if(account_ok(s,0,s->endpoint->now_tick)==0u){loss(s,ST_ACCOUNT_LOSS,ST_STOPPED,1);return;}
        feedback(s);if((flags_of(s)&ST_LOSS)!=0u)return;
    }
    phase=s->bytes[ST_PHASE];
    if(phase==0u && s->endpoint->now_tick<r64(s->bytes+ST_NEXT))return;
    if(phase<2u){
        driver(s,phase,0,r64(s->bytes+ST_LEASE),report);
        if((flags_of(s)&ST_LOSS)==0u)accept_observation(s,phase,report);
        if((flags_of(s)&ST_LOSS)==0u)s->bytes[ST_PHASE]=(uint8_t)(phase+1u);
    }else{
        evaluate(s,report);
        if((flags_of(s)&ST_LOSS)==0u){
            s->bytes[ST_PHASE]=0;
            if(s->endpoint->now_tick>=ABSENT-r16(s->arena->configuration+16)){unknown(s,ST_COUNTER);return;}
            w64(s->bytes+ST_NEXT,s->endpoint->now_tick+r16(s->arena->configuration+16));
        }
    }
}
