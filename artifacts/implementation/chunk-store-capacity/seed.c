#define _POSIX_C_SOURCE 200809L
/* Original full-geometry fixture builder/reader; RAM sync is only a counter. */
#include "bridge.c"
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

enum { SEED_BLOCKS=4096, SEED_BYTES=4096*4096 };
static unsigned char ram[SEED_BYTES], safe_ram[SEED_BYTES];
static unsigned long long read_calls, program_calls, erase_calls, sync_calls;
static int read_only;
static int valid(uint32_t block,uint32_t off,uint32_t n) {
    return block<SEED_BLOCKS && off<=4096 && n<=4096-off && off%16==0 && n%16==0;
}
static int ram_read(uint32_t block,uint32_t off,void *buf,uint32_t n) {
    if(!valid(block,off,n)) return LFS_ERR_IO;
    memcpy(buf,ram+block*4096+off,n); read_calls++; return 0;
}
static int ram_prog(uint32_t block,uint32_t off,const void *buf,uint32_t n) {
    if(read_only || !valid(block,off,n)) return LFS_ERR_IO;
    unsigned char *dest=ram+block*4096+off;
    const unsigned char *src=buf;
    for(uint32_t i=0;i<n;i++) if((dest[i]&src[i])!=src[i]) return LFS_ERR_IO;
    memcpy(dest,src,n); program_calls++; return 0;
}
static int ram_erase(uint32_t block) {
    if(read_only || block>=SEED_BLOCKS) return LFS_ERR_IO;
    memset(ram+block*4096,0xff,4096); erase_calls++; return 0;
}
static int ram_sync(void) { if(read_only) return LFS_ERR_IO; sync_calls++; return 0; }
static void check(int code) { if(code<0) { fprintf(stderr,"unexpected littlefs error %d\n",code); exit(2); } }
static void fail(const char *message) { fprintf(stderr,"%s\n",message); exit(3); }
static void dump(const char *path,const unsigned char *data) {
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(fd<0) fail("exclusive raw image creation failed");
    if(posix_fallocate(fd,0,SEED_BYTES)!=0) fail("raw image preallocation failed");
    size_t done=0;
    while(done<SEED_BYTES) {
        ssize_t n=write(fd,data+done,SEED_BYTES-done);
        if(n<=0) fail("raw image write failed");
        done+=(size_t)n;
    }
    if(fsync(fd)!=0 || close(fd)!=0) fail("raw image synchronization failed");
}
static struct bridge *new_bridge(void) {
    struct bridge *x=hm_new(ram_read,ram_prog,ram_erase,ram_sync,SEED_BLOCKS);
    if(!x) fail("bridge allocation failed");
    return x;
}
static int build(void) {
    memset(ram,0xff,sizeof(ram));
    struct bridge *x=new_bridge(); check(hm_format(x)); check(hm_mount(x));
    check(hm_write(x,"state","seed-placeholder",16));
    check(hm_mkdir(x,"i0000000000000001"));
    unsigned char data[4096]; memset(data,'A',sizeof(data));
    uint32_t success=0,safe_count=0; int safe_used=hm_used(x),error=0;
    check(safe_used); memcpy(safe_ram,ram,sizeof(ram));
    for(uint32_t i=0;i<4096;i++) {
        char path[64]; snprintf(path,sizeof(path),"i0000000000000001/c%08x",i);
        int rc=hm_write(x,path,data,sizeof(data));
        if(rc<0) { error=rc; break; }
        success=i+1;
        if(success%16==0) {
            int used=hm_used(x); check(used);
            if(used<=SEED_BLOCKS-32) {
                safe_count=success; safe_used=used;
                memcpy(safe_ram,ram,sizeof(ram));
            }
        }
    }
    int exhausted_used=hm_used(x); check(exhausted_used);
    dump("ram-exhausted.bin",ram);
    dump("safe-before-namespace.bin",safe_ram);
    hm_free(x);
    if(error!=LFS_ERR_NOSPC || safe_count==0 || safe_count>=success) fail("allocator boundary not established");
    printf("{\"status\":\"prepared\",\"blockCount\":%d,\"blockBytes\":4096,"
           "\"successfulChunks\":%u,\"failedIndex\":%u,\"failureCode\":%d,"
           "\"safeChunks\":%u,\"safeUsedBlocks\":%d,\"usedAtFailure\":%d,"
           "\"readCalls\":%llu,\"programCalls\":%llu,\"eraseCalls\":%llu,"
           "\"syncCalls\":%llu,\"ramOnly\":true}\n",
           SEED_BLOCKS,success,success,error,safe_count,safe_used,exhausted_used,
           read_calls,program_calls,erase_calls,sync_calls);
    return 0;
}
static unsigned count_arg(const char *text) {
    char *end; unsigned long number=strtoul(text,&end,10);
    if(!*text || *end || number>4096) fail("invalid chunk count");
    return (unsigned)number;
}
static int inspect(const char *path,unsigned count,unsigned base_count) {
    if(base_count>count) fail("invalid prefix count");
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    struct stat info;
    if(fd<0 || flock(fd,LOCK_EX|LOCK_NB)!=0 || fstat(fd,&info)!=0 || !S_ISREG(info.st_mode) || info.st_size!=SEED_BYTES)
        fail("raw source is not an owned readable finite image");
    size_t done=0;
    while(done<SEED_BYTES) {
        ssize_t n=read(fd,ram+done,SEED_BYTES-done);
        if(n<=0) fail("raw source read failed");
        done+=(size_t)n;
    }
    read_only=1;
    struct bridge *x=new_bridge(); check(hm_mount(x));
    unsigned char data[4096];
    for(unsigned i=0;i<count;i++) {
        char name[64]; snprintf(name,sizeof(name),"i0000000000000001/c%08x",i);
        int n=hm_read(x,name,data,sizeof(data));
        if(n!=4096) fail("referenced chunk length mismatch");
        unsigned char byte=i<base_count ? 'A':'B';
        for(unsigned j=0;j<4096;j++) if(data[j]!=byte) fail("referenced chunk payload mismatch");
    }
    int used=hm_used(x); check(used); hm_free(x);
    if(program_calls || erase_calls || sync_calls) fail("read pass mutated RAM");
    if(close(fd)!=0) fail("raw source close failed");
    printf("{\"status\":\"verified\",\"chunks\":%u,\"baseChunks\":%u,"
           "\"payloadBytes\":%u,\"uniqueReachableBlocks\":%d,\"readCalls\":%llu,"
           "\"programCalls\":0,\"eraseCalls\":0,\"syncCalls\":0,\"readOnly\":true}\n",
           count,base_count,count*4096,used,read_calls);
    return 0;
}
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"build")) return build();
    if(argc==5 && !strcmp(argv[1],"inspect")) return inspect(argv[2],count_arg(argv[3]),count_arg(argv[4]));
    fail("explicit build or inspect arguments required"); return 1;
}
