#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include "bridge.c"

enum { BYTES=2*1024*1024, BLOCK=4096 };
static unsigned char live[BYTES], durable[BYTES];
static unsigned reads, programs, erases, syncs, checks, cases;
#define CHECK(x) do { assert(x); ++checks; } while (0)
static void range(uint32_t block,uint32_t off,uint32_t size) {
    assert(block<BYTES/BLOCK && off<=BLOCK && size<=BLOCK-off);
}
static int read_memory(uint32_t block,uint32_t off,void *out,uint32_t size) {
    range(block,off,size);assert(off%4096==0 && size%4096==0);
    memcpy(out,live+block*BLOCK+off,size);++reads;return 0;
}
static int program(uint32_t block,uint32_t off,const void *input,uint32_t size) {
    range(block,off,size);assert(off%16==0 && size%16==0);
    const unsigned char *in=input;unsigned char *out=live+block*BLOCK+off;
    for (uint32_t i=0;i<size;++i) {assert((out[i]&in[i])==in[i]);out[i]=in[i];}
    ++programs;return 0;
}
static int erase(uint32_t block) {
    range(block,0,BLOCK);memset(live+block*BLOCK,0xff,BLOCK);++erases;return 0;
}
static int sync_memory(void) {memcpy(durable,live,BYTES);++syncs;return 0;}
static struct bridge *make(void) {
    struct bridge *x=hm_new(read_memory,program,erase,sync_memory,BYTES/BLOCK);
    assert(x && x->cfg.inline_max==512 && x->cfg.cache_size==4096);return x;
}
static struct bridge *cold(struct bridge *x) {
    unsigned before=syncs;hm_free(x);CHECK(syncs==before);
    memcpy(live,durable,BYTES);x=make();unsigned writes=programs;
    CHECK(hm_mount(x)==0);CHECK(programs==writes && syncs==before);return x;
}
static int inlined(struct bridge *x,const char *name) {
    unsigned char buffer[CACHE];struct lfs_file_config cfg={.buffer=buffer};lfs_file_t file;
    assert(lfs_file_opencfg(&x->fs,&file,name,LFS_O_RDONLY,&cfg)==0);
    int result=(file.flags&LFS_F_INLINE)!=0;
    assert(lfs_file_close(&x->fs,&file)==0);return result;
}
static void dump(const char *name,const unsigned char *data) {
    FILE *f=fopen(name,"wbx");assert(f);
    assert(fwrite(data,1,BYTES,f)==BYTES && fflush(f)==0 && fsync(fileno(f))==0);
    assert(fclose(f)==0);
}
int main(void) {
    memset(live,0xff,BYTES);memcpy(durable,live,BYTES);
    struct bridge *x=make();CHECK(hm_format(x)==0);CHECK(hm_mount(x)==0);++cases;
    const unsigned sizes[]={0,1,511,512,513,4096,16384,512,0};
    unsigned char input[INTERNAL_MAX+1],output[INTERNAL_MAX+1];
    for (unsigned v=0;v<sizeof(sizes)/sizeof(sizes[0]);++v) {
        unsigned size=sizes[v];for(unsigned i=0;i<size;++i)input[i]=(unsigned char)((i+v)%251);
        CHECK(hm_write(x,"boundary",input,size)==0);
        CHECK(hm_read(x,"boundary",output,sizeof(output))==(int)size && !memcmp(input,output,size));
        CHECK(inlined(x,"boundary")== (size<=512));CHECK(!memcmp(live,durable,BYTES));
        x=cold(x);
        CHECK(hm_read(x,"boundary",output,sizeof(output))==(int)size && !memcmp(input,output,size));
        CHECK(inlined(x,"boundary")== (size<=512));++cases;
    }
    unsigned before=programs;CHECK(hm_write(x,"too-large",input,INTERNAL_MAX+1)==LFS_ERR_FBIG);
    CHECK(programs==before);++cases;
    CHECK(hm_mkdir(x,"many")==0);
    for (unsigned i=0;i<300;++i) {
        char name[32];snprintf(name,sizeof(name),"many/n%03u",i);
        memset(input,(int)(i%251),32);CHECK(hm_write(x,name,input,32)==0);CHECK(inlined(x,name));
    }
    CHECK(hm_rename(x,"many/n000","many/renamed")==0);CHECK(hm_remove(x,"many/n001")==0);
    x=cold(x);
    for (unsigned i=0;i<300;++i) {
        if(i==1)continue;
        char name[32];
        if(i==0)strcpy(name,"many/renamed");
        else snprintf(name,sizeof(name),"many/n%03u",i);
        memset(input,(int)(i%251),32);
        CHECK(hm_read(x,name,output,sizeof(output))==32 && !memcmp(input,output,32));CHECK(inlined(x,name));
    }
    struct hm_entry entries[300];CHECK(hm_entries(x,"many",entries,300)==299);
    uint32_t type,size;CHECK(hm_stat(x,"many/n001",&type,&size)==LFS_ERR_NOENT);
    CHECK(hm_stat(x,"many/n000",&type,&size)==LFS_ERR_NOENT);++cases;
    int used=hm_used(x);CHECK(used>0 && used<BYTES/BLOCK);hm_free(x);
    CHECK(!memcmp(live,durable,BYTES));dump("ram-live.bin",live);dump("ram-durable.bin",durable);
    printf("{\"status\":\"passed\",\"cases\":%u,\"assertions\":%u,\"sizeVectors\":9,\"smallFiles\":300,\"remainingSmallFiles\":299,\"usedBlocks\":%d,\"reads\":%u,\"programs\":%u,\"erases\":%u,\"syncs\":%u,\"physicalPowerLoss\":false}\n",cases,checks,used,reads,programs,erases,syncs);
    return 0;
}
