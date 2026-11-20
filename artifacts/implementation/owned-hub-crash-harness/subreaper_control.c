/* Original fixed binding controls. No children or provider jobs are created. */
#include <errno.h>
#include <stdio.h>

int hms_subreaper_get(void);
int hms_subreaper_set(int value);
int hms_owner_signal_snapshot(void);

int main(void) {
    int original = hms_subreaper_get();
    int failed = 0, checks = 0;
#define CHECK(condition) do { checks++; if (!(condition)) { failed = 1; goto restore; } } while (0)
    CHECK(original == 0); /* Fresh exec of a forked harness child. */
    CHECK(hms_owner_signal_snapshot() == 1);
    CHECK(hms_subreaper_set(1) == 0);
    CHECK(hms_subreaper_get() == 1);
    CHECK(hms_subreaper_set(-1) == -EINVAL);
    CHECK(hms_subreaper_set(2) == -EINVAL);
    CHECK(hms_subreaper_get() == 1);
    CHECK(hms_subreaper_set(0) == 0);
    CHECK(hms_subreaper_get() == 0);
restore:
    if (original == 0 || original == 1) {
        if (hms_subreaper_set(original) != 0 || hms_subreaper_get() != original)
            return 2;
    }
    if (failed)
        return 1;
    printf("{\"checks\":%d,\"attributeRestored\":true,\"childrenCreated\":0}\n", checks);
    return 0;
}
