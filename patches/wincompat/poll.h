/* Klipper for Windows compat shim: poll() over Winsock sockets.
 *
 * The C serialqueue polls CRT fds that are always backed by Winsock
 * sockets on Windows (the serial bridge and the internal kick pipe are
 * both socketpairs).  Translate CRT fd -> SOCKET with _get_osfhandle and
 * use WSAPoll.  Also provides pipe() (as a socketpair) because mingw-w64
 * has no pipe(); serialqueue.c obtains its kick pipe through it.
 */
#ifndef KLFW_POLL_H
#define KLFW_POLL_H

#include <winsock2.h>
#include <ws2tcpip.h>
#include <io.h>
#include <fcntl.h>

#ifndef POLLRDNORM
#define POLLRDNORM 0x0100
#endif
#ifndef POLLRDBAND
#define POLLRDBAND 0x0200
#endif
#ifndef POLLIN
#define POLLIN (POLLRDNORM | POLLRDBAND)
#endif
#ifndef POLLPRI
#define POLLPRI  0x0400
#endif
#ifndef POLLOUT
#define POLLOUT  0x0010
#endif
#ifndef POLLERR
#define POLLERR  0x0001
#endif
#ifndef POLLHUP
#define POLLHUP  0x0002
#endif
#ifndef POLLNVAL
#define POLLNVAL 0x0004
#endif

/* mingw-w64's winsock2.h already typedefs struct pollfd (with a
 * SOCKET-sized fd field); reuse it when present.  POLLWRNORM is defined
 * immediately before that typedef, so it is a reliable proxy. */
#ifndef POLLWRNORM
struct pollfd {
    int fd;
    short events;
    short revents;
};
#endif

static inline int klfw_wsa_init(void)
{
    static WSADATA wsa;
    static int done = 0;
    if (!done) {
        WSAStartup(MAKEWORD(2, 2), &wsa);
        done = 1;
    }
    return 0;
}

static inline int poll(struct pollfd *fds, unsigned long nfds, int timeout)
{
    unsigned long i;
    int ret;
    WSAPOLLFD *tmp;
    klfw_wsa_init();
    /* struct pollfd uses int fd while WSAPOLLFD uses SOCKET (pointer
     * sized); copy through a temp array instead of aliasing. */
    tmp = (WSAPOLLFD *)_alloca(nfds * sizeof(WSAPOLLFD));
    for (i = 0; i < nfds; i++) {
        tmp[i].fd = (SOCKET)_get_osfhandle((int)fds[i].fd);
        /* WSAPoll only accepts these bits in .events (POLLHUP etc. are
         * output-only); callers pass POLLIN|POLLHUP as on POSIX. */
        tmp[i].events = fds[i].events & (POLLIN | POLLPRI | POLLOUT
                                         | POLLRDNORM | POLLRDBAND
                                         | POLLWRNORM | POLLWRBAND);
        tmp[i].revents = 0;
    }
    ret = WSAPoll(tmp, nfds, timeout);
    for (i = 0; i < nfds; i++) {
        short r = tmp[i].revents;
        short out = 0;
        if (r & (POLLRDNORM | POLLRDBAND | POLLIN))
            out |= POLLIN;
        if (r & POLLOUT)
            out |= POLLOUT;
        if (r & POLLERR)
            out |= POLLERR;
        if (r & POLLHUP)
            out |= POLLHUP;
        if (r & POLLNVAL)
            out |= POLLNVAL;
        fds[i].revents = out;
    }
    return ret;
}

/* socketpair-backed pipe() lives in the unistd.h shim */

#endif /* KLFW_POLL_H */
