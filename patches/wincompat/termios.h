/* Klipper for Windows compat shim: termios stub.
 * serialqueue.c calls tcflush(TCOFLUSH) before a retransmit; on Windows
 * the transport is USB CDC through a socket bridge, so a no-op is fine.
 */
#ifndef KLFW_TERMIOS_H
#define KLFW_TERMIOS_H

#define TCOFLUSH 2
#define TCIOFLUSH 3
#define TCSADRAIN 1
#define HUPCL  04000
#define ECHO   000010

struct termios {
    unsigned int c_iflag, c_oflag, c_cflag, c_lflag;
    unsigned int c_cc[8];
    unsigned int c_ispeed, c_ospeed;
};

static inline int tcflush(int fd, int queue)
{
    (void)fd;
    (void)queue;
    return 0;
}

#endif /* KLFW_TERMIOS_H */
