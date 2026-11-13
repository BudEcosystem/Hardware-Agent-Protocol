# Findings for the HMS I/O contract

## Configuration and reporting are operations

DigitalInputFirmata retains three arrays per port: reporting enable, previous
reported bits and the input-mode mask. A report only includes bits configured as
inputs. Enabling reporting immediately samples and sends a port value. Its
periodic report ignores the elapsed argument and checks enabled ports each time
the feature dispatcher calls it. This is change reporting, not a timestamped,
durable event stream or a demonstrated worst-case sample-age bound.

DigitalOutputFirmata's port write skips PWM, analog and servo modes. It also
handles digital-input bits: a requested one may enable INPUT_PULLUP, while the
ordinary port write mask only includes output pins. Thus a port write can change
electrical input configuration as well as output values. Single-pin writes check
the pin bound and output mode. Mode selection drives LOW before selecting output,
explicitly disabling PWM through the Arduino API. HMS must claim every affected
pin, timer and mode; a raw port interface cannot evade higher-level ownership.

AnalogInputFirmata enables/disables bits in an int mask, reports an immediate
sample when enabling outside reset, and otherwise samples all enabled analog
pins when the shared sampling interval elapses. The mapping helper searches the
board mapping and returns pin zero if it finds none. The report callback validates
the channel against TOTAL_ANALOG_PINS, but board-specific mapping consistency and
the int bit width remain dependencies. HMS needs explicit channel-to-pin mapping,
supported resolution, acquisition time, freshness and a bounded conversion/send
path. A requested interval alone is not evidence of acquisition timing.

## Validate before consulting mutable state or changing hardware

The extended-analog handler in AnalogOutputFirmata.h accepts any payload longer
than one byte, reads the supplied pin through Firmata.getPinMode, then selects
analogWriteInternal for analog or PWM mode. The core getter directly indexes
pinConfig without a bound check. The dispatcher forwards unhandled SysEx messages
to feature handlers without adding a pin bound. For a supplied pin outside a
board's TOTAL_PINS, this source path therefore performs an out-of-range lookup
before feature capability validation. This is a static source finding, not an
executed exploit or claim about every upstream release.

That handler also builds the value in int using shifts and optional bytes, does
not require one exact payload shape, and does not check the advertised PWM range
before forwarding it. The non-ESP32 analogWriteInternal narrows to int and calls
the selected Arduino core. Target integer width and that core's implementation
determine the final behavior; they are not qualified by this feature review.
HMS must decode fixed-width values, reject extra/truncated payloads, validate
indices and electrical/value bounds, and resolve pin mapping before any lookup
or effect. Validation against only the current sampled value is insufficient for
a parameterized PAT's entire declared input domain.

Core setPinMode changes the stored mode/state before invoking feature callbacks.
FirmataExt calls every feature's mode handler and ORs their return values; an
unknown-mode message does not roll back those earlier changes or side effects.
An HMS mode transition therefore needs its own admitted effect semantics, with
capability validation before mutation and explicit partial/unknown outcomes.
It must not treat feature discovery alone as an atomic configuration protocol.

## Reset and servo lifecycle need separate qualification

The digital and analog-output feature reset methods are empty. The example's
non-ESP32 system-reset callback first selects analog mode on analog pins and
output mode on other digital pins, then resets the registered features. The
output-mode handler drives LOW. ESP32 skips that loop. A library reset method,
board-specific reset sequence and commissioned actuator stop are consequently
different contracts; none proves physical rest for an attached load.

ServoFirmata allocates a Servo object on attachment, reuses it for reattachment,
and detaches/releases it on a mode change or reset. The source uses new Servo()
and later free(servo), without an allocation-failure branch. Its constructor
does not explicitly initialize the pointer array; the retained example uses a
global instance, whose storage initialization matters. The attach path checks
IS_PIN_SERVO but relies on the board macro/mapping for array range, whereas the
detach path adds an explicit mapped-index bound. Min/max pulse arguments are
forwarded without a local ordering or commissioned-envelope check. Servo library
allocation, attach return behavior, timer ownership and output timing have not
been followed in this packet. No memory-safety or timing claim is made for a
built target.

The consequence for HMS is a declared lifecycle: prepare a verified driver and
configuration, reserve shared resources, perform the transition, retain resulting
generation and observations, and reconcile unknown effects. Persistent programs
must retain their local ownership and outage policy across ordinary host absence;
an existing finite OP cannot become persistent merely by repeating it. Driver or
hub changes invalidate affected applicability facts and must not silently retain
old PAT qualification.

## Scope limits

The ESP32 analog-output implementation, Arduino GPIO/ADC/PWM/Servo dependencies,
all board-mapping variants and physical electrical behavior are not newly read
or tested here. Existing parser/scheduler concerns remain in the earlier review.
No raw Firmata firmware is adopted as the HMS execution runtime. These findings
provide concrete acceptance requirements for original bounded providers; they
do not establish installed Arduino, microscope or hub control.
