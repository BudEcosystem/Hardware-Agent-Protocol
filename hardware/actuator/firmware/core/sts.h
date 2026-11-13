/* Feetech STS-series (STS3215) serial-bus packet codec and the servo bus
 * transaction layer. Frame: FF FF ID LEN INSTR P1..Pn CHK, LEN = n + 2,
 * CHK = ~(ID + LEN + INSTR + sum(P)) & 0xFF (INTERFACE.md section 3). A status reply is
 * FF FF ID LEN ERR P1..Pn CHK with the same checksum rule.
 * Thread-safety: a sts_bus is single-owner; nothing here is interrupt-safe. */
#ifndef STS_H
#define STS_H

#include <stddef.h>
#include <stdint.h>

#include "arm_hw.h"

#ifdef __cplusplus
extern "C" {
#endif

#define STS_BROADCAST_ID 0xFEu
#define STS_MAX_PARAMS 48u
#define STS_FRAME_MAX (STS_MAX_PARAMS + 6u)

enum {
    STS_INSTR_PING = 0x01, STS_INSTR_READ = 0x02, STS_INSTR_WRITE = 0x03,
    STS_INSTR_REG_WRITE = 0x04, STS_INSTR_ACTION = 0x05, STS_INSTR_SYNC_READ = 0x82,
    STS_INSTR_SYNC_WRITE = 0x83
};

/* Control-table addresses (STS-series memory table as used by the LeRobot Feetech driver;
 * INTERFACE.md asks that they be checked against the STS3215 manual). */
enum {
    STS_REG_ID = 0x05, STS_REG_BAUD = 0x06, STS_REG_RETURN_DELAY = 0x07,
    STS_REG_MIN_ANGLE = 0x09, STS_REG_MAX_ANGLE = 0x0B, STS_REG_MAX_TORQUE = 0x10,
    STS_REG_OPERATING_MODE = 0x21, STS_REG_TORQUE_ENABLE = 0x28, STS_REG_ACCELERATION = 0x29,
    STS_REG_GOAL_POSITION = 0x2A, STS_REG_GOAL_TIME = 0x2C, STS_REG_GOAL_SPEED = 0x2E,
    STS_REG_TORQUE_LIMIT = 0x30, STS_REG_LOCK = 0x37, STS_REG_PRESENT_POSITION = 0x38,
    STS_REG_PRESENT_SPEED = 0x3A, STS_REG_PRESENT_LOAD = 0x3C, STS_REG_PRESENT_VOLTAGE = 0x3E,
    STS_REG_PRESENT_TEMP = 0x3F, STS_REG_MOVING = 0x42, STS_REG_PRESENT_CURRENT = 0x45
};
/* The telemetry block read in one transaction: 0x38 .. 0x46 inclusive. */
#define STS_TELEMETRY_LEN 15u

/* Operating modes (register 0x21). */
enum { STS_MODE_POSITION = 0, STS_MODE_SPEED = 1, STS_MODE_PWM = 2, STS_MODE_STEP = 3 };

/* Status-packet error bits. */
enum {
    STS_ERR_VOLTAGE = 0x01, STS_ERR_SENSOR = 0x02, STS_ERR_TEMPERATURE = 0x04,
    STS_ERR_CURRENT = 0x08, STS_ERR_ANGLE = 0x10, STS_ERR_OVERLOAD = 0x20
};

/* Checksum over ID, LEN, INSTR/ERR and the parameters (n bytes starting at ID). */
uint8_t sts_checksum(const uint8_t *id_to_params, size_t n);
/* Encode an instruction packet. Returns its length, or 0 when params do not fit. */
size_t sts_encode(uint8_t *out, size_t cap, uint8_t id, uint8_t instr, const uint8_t *params,
                  size_t n_params);
/* SYNC_WRITE: `n` servos, each `per_len` data bytes (data holds n blocks back to back). */
size_t sts_encode_sync_write(uint8_t *out, size_t cap, uint8_t addr, uint8_t per_len, size_t n,
                             const uint8_t *ids, const uint8_t *data);

typedef struct {
    uint8_t id;
    uint8_t error;
    uint8_t n;
    uint8_t params[STS_MAX_PARAMS];
} sts_status;

typedef enum {
    STS_OK = 0,
    STS_E_SHORT = -1,    /* fewer bytes than the length field announces */
    STS_E_HEADER = -2,   /* no FF FF */
    STS_E_LENGTH = -3,   /* LEN < 2 or the parameters do not fit */
    STS_E_CHECKSUM = -4
} sts_err;

/* Decode one status packet that starts at buf[0]. */
int sts_decode(const uint8_t *buf, size_t n, sts_status *out);

/* STS multi-byte registers are little endian; sign-magnitude values use bit 15. */
uint16_t sts_get16(const uint8_t *p);
void sts_put16(uint8_t *p, uint16_t v);
int32_t sts_sm_decode(uint16_t raw, unsigned sign_bit);
uint16_t sts_sm_encode(int32_t v, unsigned sign_bit);

/* ---- Bus transactions ------------------------------------------------------- */
typedef enum {
    STSB_OK = 0,
    STSB_TIMEOUT = -1,    /* no (complete) reply */
    STSB_COLLISION = -2,  /* the echoed bytes differ from what was sent */
    STSB_BAD_REPLY = -3,  /* reply failed header/length/checksum or came from another ID */
    STSB_ARG = -4
} stsb_err;

#define STS_REPLY_TIMEOUT_US 2500u
#define STS_ECHO_TIMEOUT_US 1000u

typedef struct {
    const arm_hw *hw;
    uint32_t frames, timeouts, collisions, bad_replies;
} sts_bus;

void sts_bus_init(sts_bus *bus, const arm_hw *hw);
/* Send one instruction; read and check the echo; if `reply` is non-NULL read the status
 * packet and require it to come from `id`. Broadcast IDs and reply == NULL expect no reply. */
int sts_bus_xfer(sts_bus *bus, uint8_t id, uint8_t instr, const uint8_t *params, size_t n_params,
                 sts_status *reply);
int sts_bus_ping(sts_bus *bus, uint8_t id, sts_status *reply);
/* Read len bytes at addr into out. The servo's error bits are returned in *servo_error. */
int sts_bus_read(sts_bus *bus, uint8_t id, uint8_t addr, uint8_t len, uint8_t *out,
                 uint8_t *servo_error);
/* Write data to addr and require the servo's ACK (unicast only). */
int sts_bus_write(sts_bus *bus, uint8_t id, uint8_t addr, const uint8_t *data, size_t len);
/* Write to every listed servo in one frame (no replies). */
int sts_bus_sync_write(sts_bus *bus, uint8_t addr, uint8_t per_len, size_t n, const uint8_t *ids,
                       const uint8_t *data);

#ifdef __cplusplus
}
#endif
#endif
