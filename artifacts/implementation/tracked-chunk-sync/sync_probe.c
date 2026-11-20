/* Check deferred errors on an already-synchronized, untouched file.
 * This is NOT a durability operation: it never substitutes for dirty-file fsync.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>

#ifndef HMS_SYNC_FILE_RANGE
#define HMS_SYNC_FILE_RANGE sync_file_range
#endif
_Static_assert(sizeof(off_t) == 8, "64-bit offset profile");
_Static_assert(SYNC_FILE_RANGE_WAIT_BEFORE == 1 && SYNC_FILE_RANGE_WAIT_AFTER == 4,
               "Linux wait flags");
unsigned hm_sync_abi(void) { return 1; }
int hm_sync_wait(int fd) {
    if (fd < 0) return -EINVAL;
    errno = 0;
    int rc = HMS_SYNC_FILE_RANGE(fd, 0, 0,
                                SYNC_FILE_RANGE_WAIT_BEFORE | SYNC_FILE_RANGE_WAIT_AFTER);
    if (rc == 0) return 0;
    return rc == -1 && errno > 0 ? -errno : -EIO;
}
