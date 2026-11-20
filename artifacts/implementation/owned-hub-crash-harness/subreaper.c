/* Original binding for a dedicated Linux/glibc/x86-64 test-harness process.
 * Only the calling process's subreaper attribute is changed. */
#define _POSIX_C_SOURCE 200809L
#include <features.h>
#include <errno.h>
#include <sys/prctl.h>

#if !defined(__linux__) || !defined(__GLIBC__) || !defined(__x86_64__)
#error "This binding is Linux/glibc/x86-64 only"
#endif
_Static_assert(sizeof(int) == 4, "32-bit exported integer ABI required");

int hms_subreaper_get(void) {
    int value = -1;
    if (prctl(PR_GET_CHILD_SUBREAPER, &value, 0L, 0L, 0L) != 0)
        return -errno;
    return value == 0 || value == 1 ? value : -EPROTO;
}

int hms_subreaper_set(int value) {
    if (value != 0 && value != 1)
        return -EINVAL;
    if (prctl(PR_SET_CHILD_SUBREAPER, (long)value, 0L, 0L, 0L) != 0)
        return -errno;
    return 0;
}
