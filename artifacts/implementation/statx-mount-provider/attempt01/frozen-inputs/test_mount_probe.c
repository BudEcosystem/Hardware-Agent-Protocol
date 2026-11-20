#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <sys/stat.h>
static int fake_statx(int, const char *, int, unsigned, struct statx *);
#define HMS_STATX fake_statx
#include "mount_probe.c"

static int calls, fault, when, selector, checks;
static int fake_statx(int fd, const char *path, int flags, unsigned mask,
                      struct statx *out) {
    ++calls;
    unsigned mount = selector ? STATX_MNT_ID_UNIQUE : STATX_MNT_ID;
    assert(mask == (STATX_TYPE | STATX_INO | mount));
    if (calls == 1) {
        assert(fd == 7 && !strcmp(path, ""));
        assert(flags == (AT_EMPTY_PATH | AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT));
    } else {
        assert(calls == 2 && fd == AT_FDCWD && !strcmp(path, "/fixture"));
        assert(flags == (AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT));
    }
    *out = (struct statx){.stx_mask = mask, .stx_mode = S_IFDIR | 0700,
                         .stx_mnt_id = 100, .stx_ino = 99,
                         .stx_dev_major = 8, .stx_dev_minor = 1};
    if (calls != when) return 0;
    switch (fault) {
    case 1: out->stx_mask &= ~STATX_TYPE; break;
    case 2: out->stx_mask &= ~STATX_INO; break;
    case 3: out->stx_mask &= ~mount; break;
    case 4: out->stx_mode = S_IFLNK | 0777; break;
    case 5: out->stx_mnt_id = 0; break;
    case 6: out->stx_ino = 0; break;
    case 7: errno = EACCES; return -1;
    case 8: errno = ENOSYS; return -1;
    case 9: return 1;
    case 10: return -1;
    case 11: ++out->stx_mnt_id; break;
    case 12: ++out->stx_ino; break;
    case 13: ++out->stx_dev_major; break;
    case 14: ++out->stx_dev_minor; break;
    case 15: out->stx_mask = STATX_BASIC_STATS; break;
    default: assert(0);
    }
    return 0;
}

static void zero(const struct hm_mount *out) {
    const unsigned char *p = (const void *)out;
    for (size_t i = 0; i < sizeof(*out); ++i) assert(!p[i]);
}

int main(void) {
    assert(hm_mount_abi() == 1);
    for (selector = 0; selector <= 1; ++selector) {
        struct hm_mount out;
        calls = fault = when = 0;
        assert(hm_mount_query(7, "/fixture", selector, &out) == 0);
        assert(calls == 2 && out.mount == 100 && out.inode == 99 &&
               out.major == 8 && out.minor == 1);
        ++checks;
        for (fault = 1; fault <= 15; ++fault) {
            for (when = 1; when <= 2; ++when) {
                int expected = fault <= 3 || fault == 15 ? EOPNOTSUPP :
                    fault == 4 ? ENOTDIR : fault == 7 ? EACCES :
                    fault == 8 ? ENOSYS : fault >= 11 && fault <= 14 ? EXDEV : EIO;
                calls = 0;
                memset(&out, 0xaa, sizeof(out));
                assert(hm_mount_query(7, "/fixture", selector, &out) == -expected);
                assert(calls == (when == 2 || (fault >= 11 && fault <= 14) ? 2 : 1));
                zero(&out); ++checks;
            }
        }
    }
    char huge[4097]; memset(huge, 'x', sizeof(huge)); huge[0]='/'; huge[4096]=0;
    const char *paths[] = {NULL, "", "relative", huge};
    calls = 0;
    struct hm_mount out;
    for (size_t i = 0; i < sizeof(paths)/sizeof(paths[0]); ++i) {
        memset(&out, 0xaa, sizeof(out));
        assert(hm_mount_query(7, paths[i], 1, &out) == -EINVAL);
        zero(&out); ++checks;
    }
    assert(hm_mount_query(-1, "/fixture", 1, &out) == -EINVAL); zero(&out); ++checks;
    assert(hm_mount_query(7, "/fixture", 2, &out) == -EINVAL); zero(&out); ++checks;
    assert(hm_mount_query(7, "/fixture", 1, NULL) == -EINVAL); ++checks;
    assert(calls == 0);
    printf("{\"status\":\"passed\",\"checks\":%d,\"actualMountChanges\":false}\n", checks);
    return 0;
}
