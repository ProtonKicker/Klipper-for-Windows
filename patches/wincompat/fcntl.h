/* Klipper for Windows compat shim: fcntl() for the two uses in the C
 * helper (F_GETFL/F_SETFL with O_NONBLOCK on socket-backed CRT fds).
 * The fd is translated back to its Winsock SOCKET and non-blocking mode
 * is set with ioctlsocket(FIONBIO).
 */
#ifndef KLFW_FCNTL_H
#define KLFW_FCNTL_H

#include <winsock2.h>
#include <io.h>
#include <stdarg.h>
#include <errno.h>

#ifndef F_GETFL
#define F_GETFL 3
#endif
#ifndef F_SETFL
#define F_SETFL 4
#endif
#ifndef O_NONBLOCK
#define O_NONBLOCK 0x4000
#endif
#ifndef O_RDONLY
#define O_RDONLY 0x0000
#endif

/* mingw's own fcntl.h flags (this shim replaces it) */
#ifndef _O_RDONLY
#define _O_RDONLY 0x0000
#define _O_WRONLY 0x0001
#define _O_RDWR   0x0002
#define _O_APPEND 0x0008
#define _O_RANDOM 0x0010
#define _O_SEQUENTIAL 0x0020
#define _O_TEMPORARY 0x0040
#define _O_NOINHERIT 0x0080
#define _O_CREAT  0x0100
#define _O_TRUNC  0x0200
#define _O_EXCL   0x0400
#define _O_SHORT_LIVED 0x1000
#define _O_TEXT   0x4000
#define _O_BINARY 0x8000
#define _O_WTEXT  0x10000
#define _O_U16TEXT 0x20000
#define _O_U8TEXT 0x40000
#define _O_ACCMODE (_O_RDONLY | _O_WRONLY | _O_RDWR)
#endif

static inline int fcntl(int fd, int cmd, ...)
{
    SOCKET s;
    u_long mode;
    if (fd < 0) {
        errno = EBADF;
        return -1;
    }
    s = (SOCKET)_get_osfhandle(fd);
    if (s == INVALID_SOCKET) {
        errno = EBADF;
        return -1;
    }
    mode = (cmd == F_SETFL) ? 1 : 0; /* callers only clear O_NONBLOCK */
    if (cmd == F_GETFL)
        return 0; /* nothing meaningful to report */
    if (ioctlsocket(s, FIONBIO, &mode))
        return -1;
    return 0;
}

#endif /* KLFW_FCNTL_H */
