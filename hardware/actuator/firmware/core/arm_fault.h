/* Device fault numbers carried in RESULT.fault and the `fault_code` property.
 * 0 means no fault. Documented to clients in arm.sidecar.json (x-bhms-faults). */
#ifndef ARM_FAULT_H
#define ARM_FAULT_H

enum {
    ARM_FAULT_NONE = 0,
    ARM_FAULT_ESTOP = 1,           /* E-stop pressed: rail cut, arm may have moved, re-home */
    ARM_FAULT_ESTOP_CONTACT = 2,   /* estop_fault_contact_A_or_Q2: GPIO8 high, rail > 2 V */
    ARM_FAULT_SERVO_RAIL = 3,      /* servo_rail_fault: enabled, E-stop released, rail < 9 V */
    ARM_FAULT_OVERCURRENT = 4,     /* > 4.5 A for 100 ms: rail switched off */
    ARM_FAULT_SERVO_COMM = 5,      /* a servo stopped answering on the bus */
    ARM_FAULT_SERVO_ERROR = 6,     /* a servo reported an error flag (overload, overheat, ...) */
    ARM_FAULT_TOOL_LOST = 7,       /* tool ID went open-circuit while powered */
    ARM_FAULT_TIMEOUT = 8,         /* motion did not reach its goal in time */
    ARM_FAULT_OVERTEMP = 9,        /* servo temperature at or above 70 C */
    ARM_FAULT_STOPPED = 10,        /* operation ended by STOP / cancel before completion */
    ARM_FAULT_BUS = 11,            /* servo bus collision: echo differs from what was sent */
    ARM_FAULT_LIMIT = 12,          /* a waypoint or measured pose violated a limit */
    ARM_FAULT_SELFTEST = 13,       /* boot self-test of the servo rail failed */
    ARM_FAULT_NO_POWER = 14,       /* VIN below 9 V: no actuator power (not a hardware fault) */
    ARM_FAULT_POWER_SENSE = 15,    /* INA219 unreadable while the rail is on */
    ARM_FAULT_CONFIG = 16,         /* servo EEPROM limits did not read back after programming */
    ARM_FAULT_TOOL = 17,           /* tool missing, wrong, not powered or not answering */
    ARM_FAULT_FOLLOWING = 18,      /* a joint trails its commanded waypoint by more than 15 deg (jam, lag) */
    ARM_FAULT_WATCHDOG = 19,       /* the controller reset itself: the arm may have fallen, enable again */
    ARM_FAULT_CALIBRATION = 20,    /* calibration failed or could not be stored */
    ARM_FAULT_STALL = 21           /* a tool motion stopped short of its goal (torque cap, mechanical stop) */
};

#endif
