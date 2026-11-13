/* Persistent joint calibration (raw_zero and sign per servo) in two flash sectors, kept as the
 * same CRC'd, power-fail-safe record log as the boot epoch (epoch_flash.h reclog). Every save
 * appends a new record, so the previous calibration stays valid until the new one is complete
 * (two copies at all times). Flash writes mask interrupts, including the E-stop IRQ: callers
 * save only while the servo rail is off.
 * Thread-safety: single owner. */
#ifndef ARM_CAL_STORE_H
#define ARM_CAL_STORE_H

#include "arm_params.h"
#include "epoch_flash.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CAL_MAGIC 0x314C4143u
#define CAL_PAYLOAD_BYTES (3u * ARM_NUM_SERVOS)

typedef struct {
    reclog log;
} cal_store;

void cal_store_init(cal_store *s, const epoch_flash_ops *ops);
/* Returns 1 and the newest stored calibration, or 0 when none is stored. A stored calibration
 * whose signs are not +-1 is ignored. */
int cal_store_load(const cal_store *s, arm_cal *out);
/* Append `cal`; returns 0 when it read back verified. */
int cal_store_save(const cal_store *s, const arm_cal *cal);

#ifdef __cplusplus
}
#endif
#endif
