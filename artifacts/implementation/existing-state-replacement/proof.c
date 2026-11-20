#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
#include "bridge.c"

/* Original finite persistence model, not an ext4/device power-loss emulator.
 * Within a block completed operations are ordered; selected dirty block states
 * may persist in different orders between acknowledged full sync barriers. */
enum { BLOCKS=32768, BLOCK_BYTES=4096, SLOTS=49152, MAX_EVENTS=128,
       MAX_PREP=128, MAX_FILL=8192, MAX_TRIALS=40000, MAX_DIRTY=128 };
enum { PROG=1, ERASE=2, SYNC=3, CUT=1, ERROR=2 };
struct event { unsigned kind, block, off, size; };
static unsigned *base_map, *live_map, *durable_map, *refs, *freelist;
static unsigned char *pool, erased[BLOCK_BYTES];
static unsigned top, free_count, dirty[MAX_DIRTY], dirty_count;
static struct event events[MAX_EVENTS];
static unsigned event_count, target_event, fault_mode, tear, order;
static struct event expected_trace[MAX_EVENTS];
static unsigned expected_count;
static int check_trace;
static unsigned bad_block=UINT32_MAX, bad_failures, fillers, preparations;
static unsigned trials, accepted_old, accepted_new, error_trials, cuts;
static unsigned old_size, new_size, case_number;
static unsigned char old_body[INTERNAL_MAX], new_body[INTERNAL_MAX], sibling[INTERNAL_MAX];
static const char *case_name="setup";
static int readonly, sticky, force_read_error, dumping, journal_count;
static struct bridge *active_owner;
static FILE *journal, *trace;
static jmp_buf cut_return;

static void dump_map(const char *folder, const unsigned *map);
static void die(const char *why) {
    fprintf(stderr,"MODEL_FAILURE case=%s event=%u target=%u mode=%u tear=%u order=%u reason=%s\n",
            case_name,event_count,target_event,fault_mode,tear,order,why);
    if (!dumping && base_map && durable_map && pool) {
        dumping=1; dump_map("counterexample-base",base_map); dump_map("counterexample-durable",durable_map);
        FILE *f=fopen("counterexample.json","wx");
        if(f) {fprintf(f,"{\"case\":\"%s\",\"event\":%u,\"target\":%u,\"mode\":%u,\"tear\":%u,\"order\":%u,\"reason\":\"%s\"}\n",
                       case_name,event_count,target_event,fault_mode,tear,order,why);fflush(f);fsync(fileno(f));fclose(f);}
    }
    exit(1);
}
#define CHECK(v,msg) do { if(!(v)) die(msg); } while(0)
static const unsigned char *bytes(unsigned slot) {return slot ? pool+(size_t)(slot-1)*BLOCK_BYTES : erased;}
static void drop(unsigned slot) {if(slot) {CHECK(refs[slot]>0,"reference underflow");if(!--refs[slot]) freelist[free_count++]=slot;}}
static unsigned copy_slot(unsigned from) {
    unsigned slot=free_count ? freelist[--free_count] : ++top;
    CHECK(slot<=SLOTS,"finite block pool exhausted");refs[slot]=1;
    memcpy(pool+(size_t)(slot-1)*BLOCK_BYTES,bytes(from),BLOCK_BYTES);return slot;
}
static void assign(unsigned *map,unsigned block,unsigned slot) {
    CHECK(block<BLOCKS,"map block bound");if(slot) ++refs[slot];drop(map[block]);map[block]=slot;
}
static void clone_map(unsigned *to,const unsigned *from) {
    for(unsigned b=0;b<BLOCKS;++b)assign(to,b,from[b]);
}
static unsigned char *mutable(unsigned *map,unsigned block) {
    unsigned prior=map[block];
    if(!prior || refs[prior]>1) {unsigned slot=copy_slot(prior);drop(prior);map[block]=slot;}
    return pool+(size_t)(map[block]-1)*BLOCK_BYTES;
}
static void dirty_block(unsigned block) {
    for(unsigned i=0;i<dirty_count;++i)if(dirty[i]==block)return;
    CHECK(dirty_count<MAX_DIRTY,"dirty block bound");dirty[dirty_count++]=block;
}
static int chosen(unsigned index,unsigned count,unsigned policy) {
    switch(policy) {
    case 0:return 0;
    case 1:return 1;
    case 2:return index<count/2;
    case 3:return index>=count/2;
    default:die("ordering bound");return 0;
    }
}
static void persist_selected(unsigned policy) {
    for(unsigned i=0;i<dirty_count;++i)if(chosen(i,dirty_count,policy))assign(durable_map,dirty[i],live_map[dirty[i]]);
}
static int torn_byte(unsigned index,unsigned size,unsigned pattern) {
    switch(pattern) {
    case 1:return index==0;
    case 2:return index<size/2;
    case 3:return index+1<size;
    case 4:return index%2==0;
    case 5:return 1;
    case 6:return 1;
    default:return 0;
    }
}
static void crash_image(const struct event *e,const unsigned char *input) {
    if(e->kind==SYNC) {
        /* before, first block, first half, all but last, even blocks, last, all */
        for(unsigned i=0;i<dirty_count;++i) {
            int use=tear==6 || (tear==1 && i==0) || (tear==2 && i<dirty_count/2) ||
                    (tear==3 && i+1<dirty_count) || (tear==4 && i%2==0) || (tear==5 && i+1==dirty_count);
            if(use)assign(durable_map,dirty[i],live_map[dirty[i]]);
        }
        return;
    }
    persist_selected(order);
    if(!tear)return;
    /* Persist all completed earlier operations of this block before its torn
     * operation. This explicitly excludes same-block reorder/collateral damage. */
    assign(durable_map,e->block,live_map[e->block]);
    unsigned char *out=mutable(durable_map,e->block);
    for(unsigned i=0;i<e->size;++i)if(torn_byte(i,e->size,tear)) {
        unsigned char desired=e->kind==ERASE ? 0xff : input[i];
        if(tear==5)out[e->off+i]= e->kind==ERASE ? (unsigned char)(out[e->off+i]|0x55) :
                                                  (unsigned char)(out[e->off+i] & (desired|0xaa));
        else out[e->off+i]=desired;
    }
}
static int event(unsigned kind,unsigned block,unsigned off,unsigned size,const void *input) {
    CHECK(!readonly,"read-only inspection requested mutation");
    if(sticky)return LFS_ERR_IO;
    CHECK(event_count<MAX_EVENTS,"per-operation event bound");
    events[event_count++]=(struct event){kind,block,off,size};
    if(check_trace) {
        CHECK(event_count<=expected_count,"event sequence grew");
        const struct event *e=&expected_trace[event_count-1];
        CHECK(e->kind==kind && e->block==block && e->off==off && e->size==size,"event trace drift");
    }
    if(target_event && event_count==target_event) {
        crash_image(&events[event_count-1],input);
        if(fault_mode==CUT)longjmp(cut_return,1);
        CHECK(fault_mode==ERROR,"fault kind");sticky=1;return LFS_ERR_IO;
    }
    if(kind!=SYNC && block==bad_block) {++bad_failures;return LFS_ERR_CORRUPT;}
    return 0;
}
static int rd_memory(uint32_t block,uint32_t off,void *output,uint32_t size) {
    CHECK(block<BLOCKS && off<=BLOCK_BYTES && size<=BLOCK_BYTES-off,"read range");
    CHECK(off%4096==0 && size%4096==0,"read alignment");
    if(sticky)return LFS_ERR_IO;
    if(force_read_error) {force_read_error=0;sticky=1;return LFS_ERR_IO;}
    memcpy(output,bytes((readonly?durable_map:live_map)[block])+off,size);return 0;
}
static int pg_memory(uint32_t block,uint32_t off,const void *input,uint32_t size) {
    CHECK(block<BLOCKS && off<=BLOCK_BYTES && size<=BLOCK_BYTES-off && off%16==0 && size%16==0,"program range");
    int rc=event(PROG,block,off,size,input);if(rc)return rc;
    unsigned char *out=mutable(live_map,block);const unsigned char *in=input;
    for(unsigned i=0;i<size;++i) {CHECK((out[off+i]&in[i])==in[i],"program requires erase");out[off+i]=in[i];}
    dirty_block(block);return 0;
}
static int er_memory(uint32_t block) {
    CHECK(block<BLOCKS,"erase range");int rc=event(ERASE,block,0,BLOCK_BYTES,NULL);if(rc)return rc;
    assign(live_map,block,0);dirty_block(block);return 0;
}
static int sy_memory(void) {
    int rc=event(SYNC,0,0,0,NULL);if(rc)return rc;
    clone_map(durable_map,live_map);dirty_count=0;return 0;
}
static struct bridge *owner(void) {
    struct bridge *x=hm_new(rd_memory,pg_memory,er_memory,sy_memory,BLOCKS);
    CHECK(x && x->cfg.block_size==4096 && x->cfg.block_count==32768 && x->cfg.inline_max==512,"exact geometry");
    return x;
}
static void pattern(unsigned char *body,unsigned size,unsigned salt) {
    for(unsigned i=0;i<size;++i)body[i]=(unsigned char)((i*131u+salt+(i>>3))&255u);
}
static void quiet(void) {event_count=0;target_event=0;fault_mode=0;sticky=0;force_read_error=0;dirty_count=0;bad_failures=0;}
static void base_from_durable(void) {clone_map(base_map,durable_map);}
static void reset(void) {clone_map(live_map,base_map);clone_map(durable_map,base_map);quiet();readonly=0;}
static void get_pair(struct bridge *x,lfs_block_t pair[2]) {
    unsigned char cache[CACHE];struct lfs_file_config cfg={.buffer=cache};lfs_file_t file;
    CHECK(lfs_file_opencfg(&x->fs,&file,"node/state",LFS_O_RDONLY,&cfg)==0,"inspect target pair open");
    pair[0]=file.m.pair[0];pair[1]=file.m.pair[1];CHECK(lfs_file_close(&x->fs,&file)==0,"inspect target pair close");
}
static void exact_file(struct bridge *x,const char *name,const unsigned char *expected,unsigned size) {
    unsigned char output[INTERNAL_MAX];int amount=hm_read(x,name,output,sizeof(output));
    CHECK(amount==(int)size && !memcmp(output,expected,size),"sibling/full-body mismatch");
}
static int inspect(int acknowledged,lfs_block_t pair[2]) {
    unsigned saved_events=event_count;readonly=1;sticky=0;force_read_error=0;
    struct bridge *x=owner();CHECK(hm_mount(x)==0,"cold read-only mount");
    unsigned char output[INTERNAL_MAX];int amount=hm_read(x,"node/state",output,sizeof(output));
    int is_old=amount==(int)old_size && !memcmp(output,old_body,old_size);
    int is_new=amount==(int)new_size && !memcmp(output,new_body,new_size);
    CHECK(is_old || is_new,"neither old nor complete new");CHECK(!acknowledged || is_new,"acknowledged state lost");
    pattern(sibling,sizeof(sibling),37);exact_file(x,"node/sibling-large",sibling,sizeof(sibling));
    exact_file(x,"node/sibling-small",(const unsigned char *)"SIBLING",7);
    struct hm_entry entries[4];CHECK(hm_entries(x,"node",entries,4)==3,"node namespace count");
    unsigned mask=0;
    for(unsigned i=0;i<3;++i) {
        CHECK(entries[i].type==LFS_TYPE_REG,"node entry type");
        if(!strcmp(entries[i].name,"state"))mask|=1;
        else if(!strcmp(entries[i].name,"sibling-small"))mask|=2;
        else if(!strcmp(entries[i].name,"sibling-large"))mask|=4;
        else die("unexpected sibling name");
    }
    CHECK(mask==7,"node namespace exact");
    if(fillers) {
        unsigned sample[3]={0,fillers/2,fillers-1};pattern(sibling,sizeof(sibling),55);
        for(unsigned i=0;i<3;++i) {char name[32];snprintf(name,sizeof(name),"fill/f%04u",sample[i]);exact_file(x,name,sibling,sizeof(sibling));}
    }
    if(pair)get_pair(x,pair);
    hm_free(x);CHECK(event_count==saved_events,"read-only callbacks changed");readonly=0;
    return is_new ? 1 : 0;
}
static void sync_journals(void) {
    CHECK(fflush(journal)==0 && fsync(fileno(journal))==0,"proof journal flush");
    CHECK(fflush(trace)==0 && fsync(fileno(trace))==0,"trace journal flush");journal_count=0;
}
static int trial(unsigned which,unsigned mode,unsigned shape,unsigned persistence,int log_it) {
    CHECK(++trials<=MAX_TRIALS,"trial bound");reset();
    active_owner=owner();CHECK(hm_mount(active_owner)==0,"trial mount");
    event_count=0;target_event=which;fault_mode=mode;tear=shape;order=persistence;
    int interrupted=setjmp(cut_return);int rc=LFS_ERR_IO;
    if(!interrupted)rc=hm_replace_existing(active_owner,"node/state",new_body,new_size);
    /* Deliberately abandon the file/owner. Do not call hm_free/lfs_unmount or
     * lfs_file_close here: no post-cut graceful flushing may manufacture proof. */
    free(active_owner);active_owner=NULL;
    if(which)CHECK(event_count==which || mode==ERROR,"cut position reached");
    if(mode==CUT)CHECK(interrupted,"cut did not drop owner");
    if(mode==ERROR)CHECK(rc<0 && sticky,"I/O error did not propagate");
    if(!mode)CHECK(rc==0,"normal replacement failed");
    int outcome=inspect(rc==0,NULL);
    if(outcome)++accepted_new;else ++accepted_old;
    if(mode==CUT)++cuts;
    if(mode==ERROR)++error_trials;
    if(log_it) {
        fprintf(journal,"{\"case\":\"%s\",\"event\":%u,\"mode\":%u,\"tear\":%u,\"order\":%u,\"outcome\":\"%s\",\"acknowledged\":%s}\n",
                case_name,which,mode,shape,persistence,outcome?"new":"old",rc==0?"true":"false");
        if(++journal_count>=64)sync_journals();
    }
    return outcome;
}
static void prepare(unsigned from,unsigned to) {
    for(unsigned b=0;b<BLOCKS;++b) {assign(base_map,b,0);assign(live_map,b,0);assign(durable_map,b,0);}
    quiet();readonly=0;check_trace=0;bad_block=UINT32_MAX;fillers=0;preparations=0;old_size=from;new_size=to;
    pattern(old_body,from,11);pattern(new_body,to,23);pattern(sibling,sizeof(sibling),37);
    struct bridge *x=owner();CHECK(hm_format(x)==0 && hm_mount(x)==0,"format/mount");event_count=0;
    CHECK(hm_mkdir(x,"node")==0,"node mkdir");event_count=0;
    CHECK(hm_write(x,"node/state",old_body,old_size)==0,"seed target");event_count=0;
    CHECK(hm_write(x,"node/sibling-small","SIBLING",7)==0,"seed small sibling");event_count=0;
    CHECK(hm_write(x,"node/sibling-large",sibling,sizeof(sibling))==0,"seed large sibling");
    hm_free(x);base_from_durable();quiet();inspect(0,NULL);
}
static void compaction(int relocation) {
    for(unsigned i=0;i<MAX_PREP;++i) {
        reset();readonly=1;lfs_block_t pair[2];struct bridge *x=owner();CHECK(hm_mount(x)==0,"pair mount");get_pair(x,pair);hm_free(x);readonly=0;
        trial(0,0,0,0,0);int compact=0;
        for(unsigned j=0;j<event_count;++j)if(events[j].kind==ERASE && (events[j].block==pair[0] || events[j].block==pair[1]))compact=1;
        ++preparations;
        if(compact) {
            if(relocation) {
                bad_block=pair[1];trial(0,0,0,0,0);
                CHECK(bad_failures>0,"relocation bad block not exercised");
                lfs_block_t after[2];inspect(1,after);
                CHECK((after[0]!=pair[0] && after[0]!=pair[1]) || (after[1]!=pair[0] && after[1]!=pair[1]),"metadata relocation not observed");
            }
            return;
        }
        base_from_durable();old_size=new_size;memcpy(old_body,new_body,new_size);pattern(new_body,new_size,24+i);
    }
    die("bounded compaction preparation gap");
}
static void nearfull(void) {
    reset();struct bridge *x=owner();CHECK(hm_mount(x)==0,"nearfull mount");CHECK(hm_mkdir(x,"fill")==0,"fill mkdir");
    pattern(sibling,sizeof(sibling),55);int used=hm_used(x);CHECK(used>0,"used blocks");
    for(unsigned i=0;i<MAX_FILL && used<BLOCKS-32;++i) {
        char name[32];snprintf(name,sizeof(name),"fill/f%04u",i);event_count=0;
        CHECK(hm_write(x,name,sibling,sizeof(sibling))==0,"near-full preparation failed before occupancy threshold");
        ++fillers;
        if(i%64==0 || used>BLOCKS-512) {used=hm_used(x);CHECK(used>0,"nearfull used");}
    }
    used=hm_used(x);CHECK(used>=BLOCKS-32 && used<BLOCKS,"near-full occupancy not established");
    hm_free(x);base_from_durable();quiet();inspect(0,NULL);
    fprintf(trace,"{\"case\":\"%s\",\"nearFullUsedBlocks\":%d,\"totalBlocks\":%u,\"fillers\":%u}\n",case_name,used,BLOCKS,fillers);
}
static void refusals(void) {
    reset();struct bridge *x=owner();CHECK(hm_mount(x)==0,"refusal mount");event_count=0;
    CHECK(hm_replace_existing(x,"node/missing",new_body,new_size)==LFS_ERR_NOENT,"missing state created");
    CHECK(event_count==0 && hm_stat(x,"node/missing",&(uint32_t){0},&(uint32_t){0})==LFS_ERR_NOENT,"missing refusal changed namespace");
    CHECK(hm_replace_existing(x,"node",new_body,new_size)==LFS_ERR_ISDIR && event_count==0,"directory replacement accepted");
    CHECK(hm_replace_existing(x,"node/state",new_body,INTERNAL_MAX+1)==LFS_ERR_FBIG && event_count==0,"size bound accepted");
    force_read_error=1;CHECK(hm_replace_existing(x,"node/state",new_body,new_size)<0 && sticky,"read failure not propagated");
    free(x);inspect(0,NULL);
}
static void matrix(void) {
    refusals();trial(0,0,0,0,1);unsigned total=event_count;struct event expected[MAX_EVENTS];memcpy(expected,events,sizeof(expected));
    CHECK(total>0,"empty mutation trace");
    expected_count=total;memcpy(expected_trace,expected,sizeof(expected_trace));check_trace=1;
    for(unsigned i=0;i<total;++i)fprintf(trace,"{\"case\":\"%s\",\"event\":%u,\"kind\":%u,\"block\":%u,\"offset\":%u,\"size\":%u}\n",case_name,i+1,expected[i].kind,expected[i].block,expected[i].off,expected[i].size);
    for(unsigned i=0;i<total;++i) {
        unsigned policies=expected[i].kind==SYNC?1:4;
        for(unsigned p=0;p<policies;++p)for(unsigned t=0;t<7;++t)trial(i+1,CUT,t,p,1);
        for(unsigned t=0;t<=6;t+=6)trial(i+1,ERROR,t,0,1);
    }
    check_trace=0;sync_journals();++case_number;
    printf("{\"case\":\"%s\",\"status\":\"passed\",\"events\":%u,\"preparations\":%u,\"fillers\":%u}\n",case_name,total,preparations,fillers);fflush(stdout);
}
static void dump_map(const char *folder,const unsigned *map) {
    if(mkdir(folder,0700)!=0)return;
    for(unsigned chunk=0;chunk<8;++chunk) {
        char name[80];snprintf(name,sizeof(name),"%s/chunk-%02u",folder,chunk);FILE *f=fopen(name,"wbx");if(!f)return;
        for(unsigned b=chunk*4096;b<(chunk+1)*4096;++b)if(fwrite(bytes(map[b]),1,BLOCK_BYTES,f)!=BLOCK_BYTES)break;
        fflush(f);fsync(fileno(f));fclose(f);
    }
}
int main(int argc,char **argv) {
    umask(0077);CHECK(argc==2,"fixed scope argument required");
    memset(erased,0xff,sizeof(erased));pool=malloc((size_t)SLOTS*BLOCK_BYTES);
    refs=calloc(SLOTS+1,sizeof(unsigned));freelist=calloc(SLOTS+1,sizeof(unsigned));
    base_map=calloc(BLOCKS,sizeof(unsigned));live_map=calloc(BLOCKS,sizeof(unsigned));durable_map=calloc(BLOCKS,sizeof(unsigned));
    CHECK(pool && refs && freelist && base_map && live_map && durable_map,"model allocation");
    journal=fopen("proof.jsonl","wx");trace=fopen("events.jsonl","wx");CHECK(journal && trace,"new journal required");
    if(!strcmp(argv[1],"basic")) {
        const unsigned sizes[][2]={{0,0},{0,1},{1,0},{1,1},{511,512},{512,513},{513,512},{513,16384},{16384,513},{16384,16384}};
        for(unsigned i=0;i<sizeof(sizes)/sizeof(sizes[0]);++i) {char label[48];snprintf(label,sizeof(label),"basic-%u-to-%u",sizes[i][0],sizes[i][1]);case_name=label;prepare(sizes[i][0],sizes[i][1]);matrix();}
    } else if(!strcmp(argv[1],"metadata")) {
        case_name="inline-compaction";prepare(511,511);compaction(0);matrix();
        case_name="outlined-compaction";prepare(513,513);compaction(0);matrix();
        case_name="inline-relocation";prepare(511,511);compaction(1);matrix();
        case_name="outlined-relocation";prepare(513,513);compaction(1);matrix();
    } else if(!strcmp(argv[1],"nearfull")) {
        case_name="near-full-growth";prepare(512,16384);nearfull();matrix();
    } else die("unknown scope");
    sync_journals();fclose(journal);fclose(trace);
    printf("{\"status\":\"passed\",\"cases\":%u,\"trials\":%u,\"cutTrials\":%u,\"errorTrials\":%u,\"oldOutcomes\":%u,\"newOutcomes\":%u,\"geometryBytes\":134217728,\"physicalPowerLoss\":false,\"hierarchyAdopted\":false}\n",case_number,trials,cuts,error_trials,accepted_old,accepted_new);
    free(pool);free(refs);free(freelist);free(base_map);free(live_map);free(durable_map);return 0;
}
