/* Klipper for Windows compat shim: unistd.h with a socketpair-backed
 * pipe() (mingw-w64 has no pipe(); serialqueue.c gets its kick pipe
 * through it).  The CRT fds returned behave for read()/write() like
 * POSIX pipes because Winsock sockets support ReadFile/WriteFile.
 */
#ifndef KLFW_UNISTD_H
#define KLFW_UNISTD_H

#include <winsock2.h>
#include <ws2tcpip.h>
#include <io.h>
#include <process.h>
#include <errno.h>
#include "fcntl.h"

typedef long long ssize_t;

/* UCRT read()/write() reject socket-backed CRT fds (EINVAL); route fds
 * that wrap Winsock sockets through recv()/send() instead.  The C helper
 * only ever touches sockets (serial bridge, kick pipe) or plain files.
 * Redirected by macro because mingw's io.h already declares the POSIX
 * names with fixed signatures. */
static inline int klfw_fd_is_socket(int fd)
{
    SOCKET s = (SOCKET)_get_osfhandle(fd);
    int type = 0;
    int len = sizeof(type);
    if (s == INVALID_SOCKET)
        return 0;
    return getsockopt(s, SOL_SOCKET, SO_TYPE, (char *)&type, &len) == 0;
}

static inline int klfw_read(int fd, void *buf, unsigned int count)
{
    int r;
    if (count > INT_MAX)
        count = INT_MAX;
    if (klfw_fd_is_socket(fd)) {
        r = recv((SOCKET)_get_osfhandle(fd), (char *)buf, (int)count, 0);
        if (r < 0) {
            errno = EIO;
            return -1;
        }
        return r;
    }
    return _read(fd, buf, count);
}

static inline int klfw_write(int fd, const void *buf, unsigned int count)
{
    int r;
    if (count > INT_MAX)
        count = INT_MAX;
    if (klfw_fd_is_socket(fd)) {
        r = send((SOCKET)_get_osfhandle(fd), (const char *)buf, (int)count, 0);
        if (r < 0) {
            errno = EIO;
            return -1;
        }
        return r;
    }
    return _write(fd, buf, count);
}

#define read klfw_read
#define write klfw_write

static inline int klfw_pipe_wsa_init(void)
{
    static WSADATA wsa;
    static int done = 0;
    if (!done) {
        WSAStartup(MAKEWORD(2, 2), &wsa);
        done = 1;
    }
    return 0;
}

static inline int pipe(int fds[2])
{
    SOCKET listener, client, server;
    struct sockaddr_in addr;
    int len = sizeof(addr);
    klfw_pipe_wsa_init();
    listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listener == INVALID_SOCKET)
        return -1;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = 0;
    if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) ||
        listen(listener, 1) ||
        getsockname(listener, (struct sockaddr *)&addr, &len)) {
        closesocket(listener);
        return -1;
    }
    client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (client == INVALID_SOCKET ||
        connect(client, (struct sockaddr *)&addr, sizeof(addr))) {
        closesocket(listener);
        if (client != INVALID_SOCKET)
            closesocket(client);
        return -1;
    }
    server = accept(listener, NULL, NULL);
    closesocket(listener);
    if (server == INVALID_SOCKET) {
        closesocket(client);
        return -1;
    }
    fds[0] = _open_osfhandle((intptr_t)server, _O_RDWR | _O_NOINHERIT);
    fds[1] = _open_osfhandle((intptr_t)client, _O_RDWR | _O_NOINHERIT);
    if (fds[0] < 0 || fds[1] < 0)
        return -1;
    return 0;
}

#define getpid _getpid

#endif /* KLFW_UNISTD_H */
