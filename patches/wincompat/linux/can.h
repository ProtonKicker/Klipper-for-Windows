/* Klipper for Windows compat shim: minimal linux/can.h.
 * serialqueue.c includes <linux/can.h> for the SocketCAN transport,
 * which is unused on Windows (USB serial only); the struct definitions
 * just need to compile.
 */
#ifndef KLFW_CAN_H
#define KLFW_CAN_H

#include <stdint.h>

#define CAN_SFF_ID 0x7FF
#define CAN_MAX_DLEN 8

struct can_frame {
    uint32_t can_id;
    union {
        uint32_t can_dlc;
        uint32_t len;
    };
    uint8_t data[CAN_MAX_DLEN] __attribute__((aligned(8)));
};

#define CAN_EFF_FLAG 0x80000000
#define CAN_RTR_FLAG 0x40000000
#define CAN_ERR_FLAG 0x20000000
#define CAN_EFF_ID_BITS 29
#define CAN_SFF_ID_BITS 11
#define CAN_EFF_MASK ((1UL << CAN_EFF_ID_BITS) - 1)
#define CAN_SFF_MASK ((1UL << CAN_SFF_ID_BITS) - 1)

#endif /* KLFW_CAN_H */
