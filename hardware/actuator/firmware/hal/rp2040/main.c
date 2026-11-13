/* BHMS Arm controller firmware entry point (RP2040, core 0 only).
 *
 * Start-up order matters for safety: every output is first driven to its reset-safe level
 * (rail off, tool off, bus driver off), the INA219 and E-stop IRQ are armed, the boot epoch is
 * persisted (before any operation can be invoked), and only then does the main loop start. The
 * rail is never switched on here: it comes up only through the `enable` action, after the
 * self-test, with the E-stop released. */
#include "arm_device.h"
#include "board.h"
#include "hardware/gpio.h"
#include "hw_rp2040.h"
#include "pico/stdlib.h"

static arm g_arm;
static arm_device g_dev;

int main(void) {
    int ina_rc = hw_init();
    stdio_init_all(); /* USB CDC */
    hw_epoch_init();
    arm_init(&g_arm, hw_arm(), 0, 0); /* nominal calibration, see README */
    if (arm_device_init(&g_dev, &g_arm, hw_bhms()) != BHMS_OK) hw_halt();
    /* An unreadable INA219 means the rail can neither be verified nor supervised: arm_tick sees
     * ina_ok == 0 and every enable is refused (PRECONDITION, power_sense); nothing is energised. */
    (void)ina_rc;
    for (;;) arm_device_poll(&g_dev);
}
