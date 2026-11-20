#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <sys/types.h>
static int fake_range(int, off_t, off_t, unsigned);
#define HMS_SYNC_FILE_RANGE fake_range
#include "sync_probe.c"
static int mode, calls;
static int fake_range(int fd, off_t offset, off_t length, unsigned flags) {
    ++calls;
    assert(fd == 7 && offset == 0 && length == 0 && flags == 5);
    switch (mode) {
    case 0: return 0;
    case 1: errno = EIO; return -1;
    case 2: errno = EINTR; return -1;
    case 3: errno = ENOSYS; return -1;
    case 4: errno = EBADF; return -1;
    case 5: return -1;
    case 6: return 1;
    default: assert(0); return -1;
    }
}
int main(void) {
    int expected[] = {0, -EIO, -EINTR, -ENOSYS, -EBADF, -EIO, -EIO};
    assert(hm_sync_abi() == 1);
    for (mode = 0; mode <= 6; ++mode) {
        calls = 0;
        assert(hm_sync_wait(7) == expected[mode] && calls == 1);
    }
    calls = 0;
    assert(hm_sync_wait(-1) == -EINVAL && calls == 0);
    puts("{\"status\":\"passed\",\"checks\":9,\"durabilityClaim\":false}");
    return 0;
}
