/* Original standalone control: changes only this test process's SIGCHLD
 * disposition, creates no children, sends no signals and restores its state. */
#define _POSIX_C_SOURCE 200809L
#include <signal.h>
#include <stdio.h>
#include <string.h>

int hms_owner_signal_snapshot(void);
static void handler(int signal_number) { (void)signal_number; }

int main(void) {
    struct sigaction original, set, after;
    unsigned checks = 0;
    int result = 1;
    if (sigaction(SIGCHLD, NULL, &original) != 0)
        return 2;
    memset(&set, 0, sizeof(set));
    if (sigemptyset(&set.sa_mask) != 0)
        return 3;
    for (unsigned disposition = 0; disposition < 3; ++disposition) {
        set.sa_handler = disposition == 0 ? SIG_DFL : disposition == 1 ? SIG_IGN : handler;
        for (unsigned no_wait = 0; no_wait < 2; ++no_wait) {
            set.sa_flags = no_wait ? SA_NOCLDWAIT : 0;
            if (sigaction(SIGCHLD, &set, NULL) != 0)
                goto restore;
            int expected = (1 << disposition) | (no_wait ? 8 : 0);
            if (hms_owner_signal_snapshot() != expected)
                goto restore;
            ++checks;
            if (sigaction(SIGCHLD, NULL, &after) != 0 ||
                after.sa_handler != set.sa_handler ||
                (after.sa_flags & SA_NOCLDWAIT) != set.sa_flags)
                goto restore;
            ++checks;
        }
    }
    result = 0;
restore:
    if (sigaction(SIGCHLD, &original, NULL) != 0)
        return 4;
    if (result == 0)
        printf("{\"cases\":6,\"checks\":%u,\"signalStateRestored\":true,\"childrenCreated\":0}\n", checks);
    return result;
}
