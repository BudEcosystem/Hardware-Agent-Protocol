/* POSIX HAL: the endpoint over a pair of file descriptors (a pty, a pipe or a
 * socket), a monotonic millisecond clock and a file-backed epoch cell. Used by
 * the native device simulator so the Python harness can drive the C endpoint
 * exactly as it drives firmware under simavr. Test/host tool, not for firmware. */
#ifndef BHMS_HAL_POSIX_H
#define BHMS_HAL_POSIX_H
#include "bhms.h"

typedef struct {
    int in_fd, out_fd;
    const char *epoch_path; /* NULL => no persistent epoch */
    bhms_hal hal;
} bhms_posix;

/* Sets in_fd non-blocking. epoch_path may be NULL. */
void bhms_posix_init(bhms_posix *p, int in_fd, int out_fd, const char *epoch_path);
/* Block up to timeout_ms until input is readable. Returns 1 when readable. */
int bhms_posix_wait(bhms_posix *p, int timeout_ms);
#endif
