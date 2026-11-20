/* Original finite littlefs bridge. The Python owner serializes all calls. */
#include "lfs.h"
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef int (*read_cb)(uint32_t, uint32_t, void *, uint32_t);
typedef int (*prog_cb)(uint32_t, uint32_t, const void *, uint32_t);
typedef int (*erase_cb)(uint32_t);
typedef int (*sync_cb)(void);
enum { CACHE=4096, INTERNAL_MAX=16384, NAME_MAXIMUM=255, MAX_BLOCKS=32768 };
struct bridge {
    lfs_t fs;
    struct lfs_config cfg;
    read_cb read;
    prog_cb prog;
    erase_cb erase;
    sync_cb sync;
    unsigned char rcache[CACHE], pcache[CACHE], lookahead[64];
    unsigned char visited[MAX_BLOCKS/8];
    uint32_t used;
    int mounted;
};
static int rd(const struct lfs_config *c, lfs_block_t b, lfs_off_t o, void *p, lfs_size_t n) {
    struct bridge *x=c->context; return x->read(b,o,p,n);
}
static int wr(const struct lfs_config *c, lfs_block_t b, lfs_off_t o, const void *p, lfs_size_t n) {
    struct bridge *x=c->context; return x->prog(b,o,p,n);
}
static int er(const struct lfs_config *c, lfs_block_t b) {
    struct bridge *x=c->context; return x->erase(b);
}
static int sy(const struct lfs_config *c) {
    struct bridge *x=c->context; return x->sync();
}
void *hm_new(read_cb r, prog_cb p, erase_cb e, sync_cb s, uint32_t blocks) {
    if (!r || !p || !e || !s || blocks<4 || blocks>MAX_BLOCKS) return NULL;
    struct bridge *x=calloc(1,sizeof(*x));
    if (!x) return NULL;
    x->read=r; x->prog=p; x->erase=e; x->sync=s;
    x->cfg=(struct lfs_config){.context=x,.read=rd,.prog=wr,.erase=er,.sync=sy,
        .read_size=4096,.prog_size=16,.block_size=4096,.block_count=blocks,
        .block_cycles=-1,.cache_size=CACHE,.lookahead_size=64,
        .read_buffer=x->rcache,.prog_buffer=x->pcache,.lookahead_buffer=x->lookahead,
        .name_max=NAME_MAXIMUM,.file_max=INTERNAL_MAX,.inline_max=512};
    return x;
}
int hm_format(struct bridge *x) { return x->mounted ? LFS_ERR_INVAL : lfs_format(&x->fs,&x->cfg); }
int hm_mount(struct bridge *x) {
    if (x->mounted) return LFS_ERR_INVAL;
    int rc=lfs_mount(&x->fs,&x->cfg);
    if (!rc) x->mounted=1;
    return rc;
}
void hm_free(struct bridge *x) {
    if (x) { if(x->mounted) lfs_unmount(&x->fs); free(x); }
}
int hm_stat(struct bridge *x, const char *path, uint32_t *type, uint32_t *size) {
    struct lfs_info info={0};
    int rc=lfs_stat(&x->fs,path,&info);
    if (!rc) { *type=info.type; *size=info.type==LFS_TYPE_REG ? info.size : 0; }
    return rc;
}
int hm_list(struct bridge *x, const char *path, char *names, uint32_t capacity) {
    lfs_dir_t dir;
    int rc=lfs_dir_open(&x->fs,&dir,path);
    if (rc) return rc;
    struct lfs_info info; uint32_t count=0;
    while ((rc=lfs_dir_read(&x->fs,&dir,&info))>0) {
        if (!strcmp(info.name,".") || !strcmp(info.name,"..")) continue;
        if (count>=capacity || strlen(info.name)>NAME_MAXIMUM) { rc=LFS_ERR_FBIG; break; }
        memset(names+count*256,0,256); strcpy(names+count*256,info.name); count++;
    }
    int close_rc=lfs_dir_close(&x->fs,&dir);
    return rc<0 ? rc : close_rc<0 ? close_rc : (int)count;
}
struct hm_entry { char name[256]; uint32_t type; uint32_t size; };
_Static_assert(sizeof(struct hm_entry)==264, "unsupported entry ABI");
int hm_entries(struct bridge *x, const char *path, struct hm_entry *entries, uint32_t capacity) {
    lfs_dir_t dir;
    int rc=lfs_dir_open(&x->fs,&dir,path);
    if(rc) return rc;
    struct lfs_info info={0}; uint32_t count=0;
    while((rc=lfs_dir_read(&x->fs,&dir,&info))>0) {
        if(!strcmp(info.name,".") || !strcmp(info.name,"..")) continue;
        if(count>=capacity || strlen(info.name)>NAME_MAXIMUM) { rc=LFS_ERR_FBIG; break; }
        memset(&entries[count],0,sizeof(entries[count]));
        strcpy(entries[count].name,info.name);
        entries[count].type=info.type;
        entries[count].size=info.type==LFS_TYPE_REG ? info.size : 0;
        count++;
    }
    int close_rc=lfs_dir_close(&x->fs,&dir);
    return rc<0 ? rc : close_rc<0 ? close_rc : (int)count;
}
int hm_read(struct bridge *x, const char *path, void *data, uint32_t cap) {
    unsigned char cache[CACHE]; struct lfs_file_config cfg={.buffer=cache}; lfs_file_t file;
    int rc=lfs_file_opencfg(&x->fs,&file,path,LFS_O_RDONLY,&cfg);
    if (rc) return rc;
    lfs_soff_t size=lfs_file_size(&x->fs,&file);
    if (size<0 || (uint32_t)size>cap) rc=size<0 ? size : LFS_ERR_FBIG;
    else { rc=lfs_file_read(&x->fs,&file,data,(lfs_size_t)size); if(rc>=0 && rc!=size) rc=LFS_ERR_IO; }
    int close_rc=lfs_file_close(&x->fs,&file);
    return rc<0 ? rc : close_rc<0 ? close_rc : rc;
}
int hm_write(struct bridge *x, const char *path, const void *data, uint32_t n) {
    if(n>INTERNAL_MAX) return LFS_ERR_FBIG;
    unsigned char cache[CACHE]; struct lfs_file_config cfg={.buffer=cache}; lfs_file_t file;
    int rc=lfs_file_opencfg(&x->fs,&file,path,LFS_O_RDWR|LFS_O_CREAT|LFS_O_TRUNC,&cfg);
    if(rc) return rc;
    rc=lfs_file_write(&x->fs,&file,data,n);
    if(rc>=0) rc=rc==(int)n ? 0 : LFS_ERR_IO;
    if(!rc) rc=lfs_file_sync(&x->fs,&file);
    int close_rc=lfs_file_close(&x->fs,&file);
    return rc<0 ? rc : close_rc;
}
int hm_mkdir(struct bridge *x,const char *p) { return lfs_mkdir(&x->fs,p); }
int hm_remove(struct bridge *x,const char *p) { return lfs_remove(&x->fs,p); }
int hm_rename(struct bridge *x,const char *a,const char *b) { return lfs_rename(&x->fs,a,b); }
int hm_sync(struct bridge *x) { return x->sync(); }
static int count_block(void *arg, lfs_block_t block) {
    struct bridge *x=arg;
    if(block>=x->cfg.block_count) return LFS_ERR_CORRUPT;
    unsigned char mask=(unsigned char)(1u<<(block%8));
    if(!(x->visited[block/8]&mask)) { x->visited[block/8]|=mask; x->used++; }
    return 0;
}
int hm_used(struct bridge *x) {
    memset(x->visited,0,sizeof(x->visited)); x->used=0;
    int rc=lfs_fs_traverse(&x->fs,count_block,x);
    return rc<0 ? rc : (int)x->used;
}
