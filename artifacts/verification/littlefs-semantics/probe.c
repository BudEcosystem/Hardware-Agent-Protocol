#define _POSIX_C_SOURCE 200809L
#include "lfs.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

enum { BLOCK = 4096, BLOCKS = 512, UNIT = 16, CACHE = 256, LENGTH = 256*1024 };
static unsigned char disk[BLOCK * BLOCKS];
static unsigned char read_cache[CACHE], prog_cache[CACHE], lookahead[64];
static unsigned long long reads, read_bytes, programs, program_bytes, erases, syncs;
static int aligned(lfs_block_t block, lfs_off_t off, lfs_size_t size) {
    return block < BLOCKS && off <= BLOCK && size <= BLOCK-off
        && off % UNIT == 0 && size % UNIT == 0;
}
static int rd(const struct lfs_config *c, lfs_block_t block, lfs_off_t off, void *buf, lfs_size_t size) {
    (void)c;
    if (!aligned(block, off, size)) return LFS_ERR_IO;
    memcpy(buf, disk + block*BLOCK + off, size);
    reads++; read_bytes += size;
    return 0;
}
static int wr(const struct lfs_config *c, lfs_block_t block, lfs_off_t off, const void *buf, lfs_size_t size) {
    (void)c;
    if (!aligned(block, off, size)) return LFS_ERR_IO;
    unsigned char *dest = disk + block*BLOCK + off;
    const unsigned char *src = buf;
    for (lfs_size_t i=0; i<size; i++) if ((dest[i] & src[i]) != src[i]) return LFS_ERR_IO;
    memcpy(dest, src, size);
    programs++; program_bytes += size;
    return 0;
}
static int erase(const struct lfs_config *c, lfs_block_t block) {
    (void)c;
    if (block >= BLOCKS) return LFS_ERR_IO;
    memset(disk + block*BLOCK, 0xff, BLOCK); erases++;
    return 0;
}
static int sync_ram(const struct lfs_config *c) { (void)c; syncs++; return 0; }
static void reset_counts(void) { reads=read_bytes=programs=program_bytes=erases=syncs=0; }
static void require_at(long long actual, long long expected, int line) {
    if (actual != expected) { fprintf(stderr, "line %d: %lld != %lld\n", line, actual, expected); exit(2); }
}
#define CHECK(call, expected) require_at((call), (expected), __LINE__)
static void image(void) {
    int fd = open("image.bin", O_WRONLY|O_CREAT|O_EXCL, 0600);
    if (fd < 0) { perror("create image"); exit(3); }
    size_t done=0;
    while (done < sizeof(disk)) {
        ssize_t n=write(fd, disk+done, sizeof(disk)-done);
        if (n<=0) { perror("write image"); exit(3); }
        done+=(size_t)n;
    }
    CHECK(fsync(fd), 0); CHECK(close(fd), 0);
}
static void make_file(lfs_t *lfs, size_t size) {
    unsigned char cache[CACHE], data[BLOCK]; memset(data, 'A', sizeof(data));
    struct lfs_file_config fc={.buffer=cache}; lfs_file_t f={0};
    CHECK(lfs_file_opencfg(lfs,&f,"data",LFS_O_CREAT|LFS_O_EXCL|LFS_O_RDWR,&fc),0);
    for(size_t i=0;i<size;i+=sizeof(data)) CHECK(lfs_file_write(lfs,&f,data,sizeof(data)),sizeof(data));
    CHECK(lfs_file_sync(lfs,&f),0); CHECK(lfs_file_close(lfs,&f),0);
}
int main(int argc, char **argv) {
    if(argc!=2 || (strcmp(argv[1],"prefix") && strcmp(argv[1],"tail")
                && strcmp(argv[1],"handles") && strcmp(argv[1],"unmount"))) return 1;
    memset(disk,0xff,sizeof(disk));
    struct lfs_config cfg={.read=rd,.prog=wr,.erase=erase,.sync=sync_ram,
        .read_size=UNIT,.prog_size=UNIT,.block_size=BLOCK,.block_count=BLOCKS,
        .block_cycles=-1,.cache_size=CACHE,.lookahead_size=sizeof(lookahead),
        .read_buffer=read_cache,.prog_buffer=prog_cache,.lookahead_buffer=lookahead,
        .file_max=LENGTH,.inline_max=(lfs_size_t)-1};
    lfs_t lfs={0}; CHECK(lfs_format(&lfs,&cfg),0); CHECK(lfs_mount(&lfs,&cfg),0);
    size_t length=(!strcmp(argv[1],"prefix") || !strcmp(argv[1],"tail")) ? LENGTH : 8192;
    make_file(&lfs,length);
    unsigned char ca[CACHE],cb[CACHE],cc[CACHE],data[BLOCK]; memset(data,'B',sizeof(data));
    struct lfs_file_config fca={.buffer=ca},fcb={.buffer=cb},fcc={.buffer=cc};
    lfs_file_t a={0},b={0},fresh={0};
    CHECK(lfs_file_opencfg(&lfs,&a,"data",LFS_O_RDWR,&fca),0);
    if(!strcmp(argv[1],"prefix") || !strcmp(argv[1],"tail")) {
        lfs_off_t pos=!strcmp(argv[1],"prefix") ? 0 : LENGTH-BLOCK;
        CHECK(lfs_file_seek(&lfs,&a,(lfs_soff_t)pos,LFS_SEEK_SET),pos);
        reset_counts();
        CHECK(lfs_file_write(&lfs,&a,data,sizeof(data)),sizeof(data));
        CHECK(lfs_file_sync(&lfs,&a),0);
        printf("{\"scenario\":\"%s\",\"fileBytes\":%d,\"changedBytes\":%d,\"offset\":%u,"
            "\"readCalls\":%llu,\"readBytes\":%llu,\"programCalls\":%llu,\"programBytes\":%llu,"
            "\"erases\":%llu,\"syncCalls\":%llu}\n",argv[1],LENGTH,BLOCK,pos,
            reads,read_bytes,programs,program_bytes,erases,syncs);
        CHECK(lfs_file_close(&lfs,&a),0);
        CHECK(lfs_file_opencfg(&lfs,&fresh,"data",LFS_O_RDONLY,&fcc),0);
        for(size_t at=0;at<length;at+=sizeof(data)) {
            CHECK(lfs_file_read(&lfs,&fresh,data,sizeof(data)),sizeof(data));
            for(size_t i=0;i<sizeof(data);i++) CHECK(data[i],at==pos ? 'B':'A');
        }
        CHECK(lfs_file_close(&lfs,&fresh),0); CHECK(lfs_unmount(&lfs),0);
    } else if(!strcmp(argv[1],"handles")) {
        CHECK(lfs_file_opencfg(&lfs,&b,"data",LFS_O_RDONLY,&fcb),0);
        CHECK(lfs_file_write(&lfs,&a,data,16),16); CHECK(lfs_file_sync(&lfs,&a),0);
        CHECK(lfs_file_read(&lfs,&b,data,16),16); int old=data[0];
        for(int i=1;i<16;i++) CHECK(data[i],old);
        CHECK(lfs_file_opencfg(&lfs,&fresh,"data",LFS_O_RDONLY,&fcc),0);
        CHECK(lfs_file_read(&lfs,&fresh,data,16),16); int latest=data[0];
        for(int i=0;i<16;i++) CHECK(data[i],'B');
        printf("{\"scenario\":\"handles\",\"existingHandleByte\":%d,\"freshHandleByte\":%d,"
               "\"sameView\":%s}\n",old,latest,old==latest ? "true":"false");
        CHECK(lfs_file_close(&lfs,&fresh),0); CHECK(lfs_file_close(&lfs,&b),0);
        CHECK(lfs_file_close(&lfs,&a),0); CHECK(lfs_unmount(&lfs),0);
    } else {
        CHECK(lfs_file_write(&lfs,&a,data,16),16);
        reset_counts(); CHECK(lfs_unmount(&lfs),0); unsigned long long unmount_syncs=syncs;
        // Old open handle is intentionally abandoned with its caller-owned buffer.
        lfs_t reopened={0}; CHECK(lfs_mount(&reopened,&cfg),0);
        CHECK(lfs_file_opencfg(&reopened,&fresh,"data",LFS_O_RDONLY,&fcc),0);
        CHECK(lfs_file_read(&reopened,&fresh,data,16),16); int after=data[0];
        for(int i=1;i<16;i++) CHECK(data[i],after);
        printf("{\"scenario\":\"unmount\",\"unmountSyncCalls\":%llu,"
               "\"reopenedByte\":%d,\"pendingWriteVisible\":%s}\n",unmount_syncs,after,after=='B' ? "true":"false");
        CHECK(lfs_file_close(&reopened,&fresh),0); CHECK(lfs_unmount(&reopened),0);
    }
    image(); return 0;
}
