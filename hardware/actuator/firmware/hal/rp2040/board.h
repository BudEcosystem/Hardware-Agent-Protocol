/* BHMS Arm controller (RP2040): pin map and flash layout.
 * Source of truth: hardware/actuator/pcb/controller.py; INTERFACE.md section 1 repeats it. */
#ifndef BHMS_ARM_BOARD_H
#define BHMS_ARM_BOARD_H

#define PIN_BUS_TX 0        /* UART0 TX -> 74AHCT1G125 input A */
#define PIN_BUS_RX 1        /* UART0 RX <- 74LVC1G125 output Y (sees its own TX: echo) */
#define PIN_BUS_TXEN_N 2    /* driver enable, active low; 10 k pull-up keeps it off in reset */
#define PIN_I2C_SDA 4
#define PIN_I2C_SCL 5
#define PIN_SERVO_EN 6      /* gate of Q4; 100 k pull-down: rail off in reset */
#define PIN_TOOL_EN 7       /* gate of Q5; 100 k pull-down */
#define PIN_ESTOP_SENSE 8   /* contact B: high = pressed / open / unplugged */
#define PIN_LED_R 11        /* active low */
#define PIN_LED_G 12
#define PIN_LED_B 13
#define PIN_ADC_TOOL_ID 26  /* ADC0 */
#define PIN_ADC_AUX1 27     /* ADC1 */
#define PIN_ADC_AUX2 28     /* ADC2 */
#define PIN_ADC_VIN 29      /* ADC3: VIN = V_adc x 11 */

#define BUS_BAUD 1000000u
#define INA219_ADDR 0x40u
#define I2C_BAUD 400000u

/* Persistent boot counter: the last two 4 KiB sectors of the 16 MiB W25Q128JV. */
#define EPOCH_REGION_BYTES (2u * 4096u)

#endif
