# Arduino AVR I/O boundaries

All six retained source files were read in full: **1,443 LF lines** from the exact Arduino AVR Boards 1.8.8 archive. The archive was already retained locally and its published package hash was checked before extracting these bounded regular members. [manifest.json](manifest.json) preserves provenance; [reading.json](reading.json) records subsequent full-file coverage. No acquired source was built, imported or executed. This is source evidence for an HMS adapter design, not hardware or electrical qualification.

## A nominal read can change output ownership

In [wiring_digital.c](source/cores/arduino/wiring_digital.c), `digitalRead` calls the PWM-disconnection helper before reading the port input. `digitalWrite` also disconnects PWM, then changes the output latch. `pinMode` changes direction and the pull-up latch; values other than the two input modes select output. Table lookups occur before checking the returned port sentinel. The [header macros](source/cores/arduino/Arduino.h) do not supply an index bound around those lookups. Therefore an HMS adapter must validate the exact installed pin and mode domain before invoking these functions, and cannot advertise this digital-read wrapper as an effect-free observation. The public [digital source](https://github.com/arduino/ArduinoCore-avr/blob/1.8.8/cores/arduino/wiring_digital.c) identifies the same version; retained archive bytes are the review authority.

## ADC and PWM operations share configuration

[wiring_analog.c](source/cores/arduino/wiring_analog.c) retains reference selection in a global variable and applies it during the subsequent read. Reading selects the converter channel/reference, starts conversion, and waits for the busy flag without an explicit software deadline. Channel masking is not validation against the commissioned package's exposed inputs. The source does not attach acquisition time, freshness, calibration or reference identity to its integer result.

`analogWrite` first selects output mode. Zero/full-scale values use digital output; intermediate values connect a timer channel and write its compare register. A pin without a supported timer falls back to a thresholded digital value. There is no local range refusal for the supplied duty value. HMS must describe these concrete effects and refuse unsupported PWM rather than silently accepting a digital substitute. The [public analog source](https://github.com/arduino/ArduinoCore-avr/blob/1.8.8/cores/arduino/wiring_analog.c) is a corroborating primary reference.

## Runtime infrastructure owns peripheral resources too

[wiring.c](source/cores/arduino/wiring.c) initializes Timer0 timekeeping, configures Timer1 and Timer2 for PWM in the applicable branches, enables the ADC and clears USART control. Thus ordinary Arduino initialization would alter peripherals already owned by the isolated HMS Timer1/UART runtime. Its timer-based delays also do not define the HMS cooperative driver-step contract. Reusing isolated I/O helpers cannot silently assume that the entire Arduino startup configuration is present or compatible.

The [standard pin map](source/variants/standard/pins_arduino.h) supplies twenty digital table entries, six declared analog inputs, timer aliases, SPI aliases and SDA/SCL aliases. Constants A6/A7 alone do not establish digital-table or board-package availability. Timer1 PWM aliases include digital pins 9 and 10, while the current HMS clock owns Timer1; registry admission must resolve that shared dependency before admitting a PWM capability. The private/header files also identify C/library and AVR headers outside this six-file review; no complete dependency or toolchain-reading claim is made here.

## Consequences for the next concrete adapter

These are design requirements inferred from the inspected source and the existing HMS ownership contract:

* Installation binds an exact board/package, port-bit map, reference, driver identity and peripheral footprint. A friendly pin label does not replace those bindings.
* Acquisition has explicit effects and claims. ADC selection/conversion owns the shared converter/reference; a truly passive port read needs an installed implementation that preserves the already-owned mode and PWM connection.
* Every actual register/bus handoff checks the current operation identity, generation, fences and exclusive cutoff. ADC work needs bounded start/poll/collect phases and a declared failure path, rather than inheriting an unbounded busy wait.
* Timer/pin/clock/UART aliases participate in one admission graph. Initialization and reconfiguration are managed lifecycle operations. A runtime clock reservation cannot be overwritten through a seemingly unrelated PWM helper.
* Reports distinguish command-latch state, converter samples and independent physical response. An electrical low or a stopped timer does not by itself prove mechanical rest or a safe installation state.

This review supplies evidence for real GPIO/ADC/PWM provider work. It does not implement that provider, qualify a microscope actuator, or promote the synthetic standing driver into physical operation.
