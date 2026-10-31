/* Klipper for Windows compat shim: prctl stub for set_thread_name().
 * mingw-w64 has no <sys/prctl.h>; thread names are cosmetic here.
 * Also guarantees CLOCK_MONOTONIC_RAW exists for pyhelper.c.
 */
#ifndef KLFW_PRCTL_H
#define KLFW_PRCTL_H

#include <time.h>

#ifndef CLOCK_MONOTONIC_RAW
#define CLOCK_MONOTONIC_RAW CLOCK_MONOTONIC
#endif

#ifndef PR_SET_NAME
#define PR_SET_NAME 15
#endif

static inline int prctl(int option, ...)
{
    (void)option;
    return 0;
}

#endif /* KLFW_PRCTL_H */
