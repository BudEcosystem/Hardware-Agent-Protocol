/* Original Linux metadata-only evaluation prototype; not a runtime provider. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

enum scan_status { SCAN_OK, SCAN_UNSAFE, SCAN_LIMIT, SCAN_OS };
struct scan {
    uint64_t files, bytes, max_files, max_bytes;
    enum scan_status status;
    int error;
};

static void fail(struct scan *s, enum scan_status status, int error) {
    if (s->status == SCAN_OK) { s->status = status; s->error = error; }
}

/* Takes ownership of fd on every path. No regular file is opened. */
static void walk(struct scan *s, int fd, unsigned depth) {
    if (depth > 10) {
        fail(s, SCAN_LIMIT, 0);
        (void)close(fd); /* Linux: never retry a failed close. */
        return;
    }
    DIR *stream = fdopendir(fd);
    if (stream == NULL) {
        int saved = errno;
        (void)close(fd);
        fail(s, SCAN_OS, saved);
        return;
    }
    int parent = dirfd(stream);
    if (parent < 0) fail(s, SCAN_OS, errno);
    while (s->status == SCAN_OK) {
        errno = 0;
        struct dirent *entry = readdir(stream);
        if (entry == NULL) {
            if (errno != 0) fail(s, SCAN_OS, errno);
            break;
        }
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) continue;
        s->files++;
        if (s->files > s->max_files) { fail(s, SCAN_LIMIT, 0); break; }
        struct stat info;
        if (fstatat(parent, entry->d_name, &info, AT_SYMLINK_NOFOLLOW) != 0) {
            fail(s, SCAN_OS, errno); break;
        }
        if (info.st_uid != getuid()) { fail(s, SCAN_UNSAFE, 0); break; }
        if (S_ISDIR(info.st_mode)) {
            if ((info.st_mode & 07777) != 0700) { fail(s, SCAN_UNSAFE, 0); break; }
            int child = openat(parent, entry->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0) { fail(s, SCAN_OS, errno); break; }
            walk(s, child, depth + 1);
        } else {
            if (!S_ISREG(info.st_mode) || info.st_nlink != 1 || (info.st_mode & 07777) != 0600) {
                fail(s, SCAN_UNSAFE, 0); break;
            }
            if (info.st_size < 0 || (uint64_t)info.st_size > s->max_bytes - s->bytes) {
                fail(s, SCAN_LIMIT, 0); break;
            }
            s->bytes += (uint64_t)info.st_size;
        }
    }
    if (closedir(stream) != 0) fail(s, SCAN_OS, errno);
}

static struct scan scan_path(const char *path, uint64_t files, uint64_t bytes) {
    struct scan s = { .max_files = files, .max_bytes = bytes, .status = SCAN_OK };
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) fail(&s, SCAN_OS, errno);
    else walk(&s, fd, 0);
    return s;
}

static int decimal(const char *text, uint64_t maximum, uint64_t *result) {
    uint64_t value = 0;
    if (*text == '\0') return 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; p++) {
        if (*p < '0' || *p > '9') return 0;
        uint64_t digit = (uint64_t)(*p - '0');
        if (digit > maximum || value > (maximum - digit) / 10) return 0;
        value = value * 10 + digit;
    }
    *result = value;
    return 1;
}

static uint64_t cpu_us(const struct rusage *usage) {
    return (uint64_t)usage->ru_utime.tv_sec * 1000000 + (uint64_t)usage->ru_utime.tv_usec
         + (uint64_t)usage->ru_stime.tv_sec * 1000000 + (uint64_t)usage->ru_stime.tv_usec;
}

int main(int argc, char **argv) {
    uint64_t files, bytes, repeats;
    if (argc != 5 || !decimal(argv[2], 262144, &files) || !decimal(argv[3], 268435456, &bytes)
            || !decimal(argv[4], 5, &repeats) || repeats == 0) return 64;
    struct scan result = scan_path(argv[1], files, bytes); /* fixed warm scan */
    struct rusage before, after;
    if (getrusage(RUSAGE_SELF, &before) != 0) return 70;
    uint64_t completed = 0;
    if (result.status == SCAN_OK) {
        for (; completed < repeats; completed++) {
            result = scan_path(argv[1], files, bytes);
            if (result.status != SCAN_OK) break;
        }
    }
    if (getrusage(RUSAGE_SELF, &after) != 0) return 70;
    const char *reason = result.status == SCAN_OK ? "OK" : result.status == SCAN_UNSAFE
        ? "QUALIFICATION_UNSAFE_FILE" : result.status == SCAN_LIMIT ? "QUALIFICATION_RETENTION_UNKNOWN" : "OS_ERROR";
    printf("{\"reason\":\"%s\",\"errno\":%d,\"files\":%" PRIu64 ",\"logicalBytes\":%" PRIu64
        ",\"scans\":%" PRIu64 ",\"cpuMicroseconds\":%" PRIu64 "}\n",
        reason, result.error, result.files, result.bytes, completed, cpu_us(&after) - cpu_us(&before));
    return result.status == SCAN_OK ? 0 : 1;
}
