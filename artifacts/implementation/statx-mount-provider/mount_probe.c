/* Private Linux mount identity query; no filesystem mutation or allocation. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>

#ifndef HMS_STATX
#define HMS_STATX statx
#endif

struct hm_mount {
    uint64_t mount;
    uint64_t inode;
    uint32_t major;
    uint32_t minor;
};

_Static_assert(sizeof(struct statx) == 256, "statx ABI size");
_Static_assert(offsetof(struct statx, stx_mnt_id) == 144, "statx mount offset");
_Static_assert(sizeof(struct hm_mount) == 24, "query ABI size");
_Static_assert(STATX_MNT_ID == 0x1000 && STATX_MNT_ID_UNIQUE == 0x4000,
               "mount mask ABI");

unsigned hm_mount_abi(void) { return 1; }

static int query(int fd, const char *path, int flags, unsigned mask,
                 struct statx *out) {
    memset(out, 0, sizeof(*out));
    errno = 0;
    int result = HMS_STATX(fd, path, flags, mask, out);
    if (result != 0) return result == -1 && errno > 0 ? -errno : -EIO;
    if ((out->stx_mask & mask) != mask) return -EOPNOTSUPP;
    if (!S_ISDIR(out->stx_mode)) return -ENOTDIR;
    if (!out->stx_mnt_id || !out->stx_ino) return -EIO;
    return 0;
}

int hm_mount_query(int fd, const char *path, int unique, struct hm_mount *out) {
    if (!out) return -EINVAL;
    memset(out, 0, sizeof(*out));
    if (fd < 0 || !path || path[0] != '/' ||
        strnlen(path, 4096) >= 4096 || (unique != 0 && unique != 1))
        return -EINVAL;
    unsigned mask = STATX_TYPE | STATX_INO |
                    (unique ? STATX_MNT_ID_UNIQUE : STATX_MNT_ID);
    int flags = AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT;
    struct statx held, named;
    int rc = query(fd, "", flags | AT_EMPTY_PATH, mask, &held);
    if (rc) return rc;
    rc = query(AT_FDCWD, path, flags, mask, &named);
    if (rc) return rc;
    if (held.stx_mnt_id != named.stx_mnt_id || held.stx_ino != named.stx_ino ||
        held.stx_dev_major != named.stx_dev_major ||
        held.stx_dev_minor != named.stx_dev_minor) return -EXDEV;
    *out = (struct hm_mount){held.stx_mnt_id, held.stx_ino,
                            held.stx_dev_major, held.stx_dev_minor};
    return 0;
}
