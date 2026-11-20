/* Read-only SIGCHLD precondition query for the explicit Linux/glibc/x86-64
 * owner profile. This does not establish the absence of another reaper or
 * prevent a later signal-disposition change. The owner must control both.
 * Return: negative errno on failure; otherwise exactly one disposition bit,
 * optionally ORed with NOCLDWAIT. No signal disposition is modified here. */
#define _POSIX_C_SOURCE 200809L
#include <features.h>
#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>

#if !defined(__linux__) || !defined(__GLIBC__) || !defined(__x86_64__)
#error "This owner precondition binding is Linux/glibc/x86-64 only"
#endif

_Static_assert(sizeof(int) == 4, "The exported scalar ABI requires 32-bit int");

enum {
    HMS_SIGCHLD_DEFAULT = 1,
    HMS_SIGCHLD_IGNORED = 2,
    HMS_SIGCHLD_CUSTOM = 4,
    HMS_SIGCHLD_NOCLDWAIT = 8
};

int hms_owner_signal_snapshot(void) {
    struct sigaction observed;
    int result;
    if (sigaction(SIGCHLD, NULL, &observed) != 0)
        return -errno;
    if (observed.sa_handler == SIG_DFL)
        result = HMS_SIGCHLD_DEFAULT;
    else if (observed.sa_handler == SIG_IGN)
        result = HMS_SIGCHLD_IGNORED;
    else
        result = HMS_SIGCHLD_CUSTOM;
    if ((observed.sa_flags & SA_NOCLDWAIT) != 0)
        result |= HMS_SIGCHLD_NOCLDWAIT;
    return result;
}
