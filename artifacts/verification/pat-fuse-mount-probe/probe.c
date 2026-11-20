/* Original bounded read-only FUSE mechanism probe. No durable storage provider. */
#define FUSE_USE_VERSION 31
#include <fuse.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

static const char document[] =
    "{\"profile\":\"hms.fuse-mechanism-probe/1\",\"readOnly\":true,"
    "\"durableStorage\":false,\"totalDiskQuotaEnforced\":false,"
    "\"backedControlCapacity\":false}\n";

static int attrs(const char *path, struct stat *out, struct fuse_file_info *fi)
{
    (void)fi;
    memset(out, 0, sizeof(*out));
    out->st_uid = getuid();
    out->st_gid = getgid();
    if (!strcmp(path, "/")) {
        out->st_mode = S_IFDIR | 0500;
        out->st_nlink = 2;
        out->st_ino = 1;
    } else if (!strcmp(path, "/probe.json")) {
        out->st_mode = S_IFREG | 0400;
        out->st_nlink = 1;
        out->st_ino = 2;
        out->st_size = (off_t)(sizeof(document) - 1);
    } else {
        return -ENOENT;
    }
    return 0;
}

static int entries(const char *path, void *buf, fuse_fill_dir_t fill,
                   off_t offset, struct fuse_file_info *fi,
                   enum fuse_readdir_flags flags)
{
    (void)fi;
    (void)flags;
    const char *names[] = {".", "..", "probe.json"};
    if (strcmp(path, "/")) return -ENOENT;
    if (offset < 0) return -EINVAL;
    for (off_t i = offset; i < 3; ++i) {
        if (fill(buf, names[i], NULL, i + 1, 0)) break;
    }
    return 0;
}

static int open_document(const char *path, struct fuse_file_info *fi)
{
    if (strcmp(path, "/probe.json")) return -ENOENT;
    if ((fi->flags & O_ACCMODE) != O_RDONLY) return -EROFS;
    fi->direct_io = 1;
    return 0;
}

static int read_document(const char *path, char *buffer, size_t count,
                         off_t offset, struct fuse_file_info *fi)
{
    (void)fi;
    if (strcmp(path, "/probe.json")) return -ENOENT;
    if (offset < 0) return -EINVAL;
    if ((uint64_t)offset >= sizeof(document) - 1) return 0;
    size_t available = sizeof(document) - 1 - (size_t)offset;
    if (count > available) count = available;
    memcpy(buffer, document + offset, count);
    return (int)count;
}

static void *started(struct fuse_conn_info *conn, struct fuse_config *config)
{
    config->entry_timeout = 0;
    config->attr_timeout = 0;
    config->negative_timeout = 0;
    config->kernel_cache = 0;
    fprintf(stderr, "ready pid=%ld uid=%ld protocol=%u.%u\n",
            (long)getpid(), (long)getuid(), conn->proto_major, conn->proto_minor);
    return NULL;
}

static void ended(void *unused)
{
    (void)unused;
    fprintf(stderr, "destroy pid=%ld\n", (long)getpid());
}

static int limit(int kind, rlim_t value)
{
    const struct rlimit setting = {value, value};
    return setrlimit(kind, &setting);
}

int main(int argc, char **argv)
{
    if (argc != 2 || argv[1][0] != '/') return 2;
    const pid_t parent = getppid();
    if (parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent)
        return 3;
    if (limit(RLIMIT_AS, 64 * 1024 * 1024) || limit(RLIMIT_CPU, 3) ||
        limit(RLIMIT_NOFILE, 64) || limit(RLIMIT_FSIZE, 16 * 1024 * 1024))
        return 4;
    alarm(20);
    if (fuse_version() != 314 || strcmp(fuse_pkgversion(), "3.14.0")) return 5;
    const struct fuse_operations operations = {
        .getattr = attrs, .readdir = entries, .open = open_document,
        .read = read_document, .init = started, .destroy = ended
    };
    char *args[] = {argv[0], "-f", "-s", "-o",
        "ro,nosuid,nodev,noexec,default_permissions,fsname=hms-probe-81,subtype=hmsprobe",
        argv[1], NULL};
    return fuse_main(6, args, &operations, NULL);
}
