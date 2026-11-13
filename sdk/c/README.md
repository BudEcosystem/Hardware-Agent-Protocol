# BHMS-Compact C library and Arduino library

Lets a small microcontroller (ATmega328P class and up) be a BHMS device. The
endpoint speaks the compact binary binding of
[spec/bhms/11-compact-binding.md](../../spec/bhms/11-compact-binding.md) over
serial; a gateway (Task 9b) holds the full description keyed by the digest the
endpoint reports and translates to JSON-RPC.

* No heap, no recursion, every buffer sized by `include/bhms_config.h`.
* Framing is `protocol/serial/frame.{c,h}`, used unchanged (decoder side). That
  layer has no encoder in C, so `src/bhms_tx.c` adds the transmit side with the
  same header, FCS-16 and byte stuffing as `frame.py` (checked against it).
* Tables live in flash on AVR (`BHMS_PROGMEM`).

```
include/bhms.h          API, wire constants, message codecs (the one header to read)
include/bhms_hal.h      the HAL a port implements
include/bhms_config.h   bounds: ring, active ops, argument/result bytes, timeouts
src/bhms_codec.c        message and value codecs (byte-exact to spec 11.2/11.4)
src/bhms_tx.c           frame encoder (host buffer and streaming-to-HAL)
src/bhms_endpoint.c     the endpoint state machine
hal/host/               host HALs: in-memory (unit tests), POSIX fd (device simulator)
arduino/BHMS/           Arduino library (self-contained copies; see scripts/sync_arduino.sh)
tests/                  C unit tests, Python pty harness (tests/host), simavr runner
tools/bhms_digest.py    sidecar JSON -> digest and `digest8` C initialiser
```

## Using it

```c
BHMS_FIELDS(led_in)  = { BHMS_BOOL() };              /* argument layout, in flash */
BHMS_FIELDS(led_out) = { BHMS_U8() };                /* result layout */
static const bhms_action actions[] BHMS_PROGMEM = {  /* index = position = compact.index */
    BHMS_ACTION(led_run, /*cancel*/0, /*flags*/0,
                BHMS_FIELDS_REF(led_in), BHMS_FIELDS_REF(led_out)) };
static const bhms_property props[] BHMS_PROGMEM = { BHMS_PROPERTY(adc_read, BHMS_U16) };
static const bhms_device dev = { {0x23,0x8a,...}, /*flags*/0, actions, 1, props, 1,
                                 /*stop*/0, /*user*/0 };
bhms_endpoint ep;
if (bhms_init(&ep, &dev, &hal) != BHMS_OK) halt();  /* persists the new boot epoch first;
                                                      a failed init leaves an inert endpoint */
for (;;) bhms_poll(&ep);            /* drain UART, process frames, watch stop pin */
```

Callbacks (all bounded, non-blocking, called from `bhms_poll`):

| Callback | Contract |
|---|---|
| `uint8_t run(user, const bhms_value *args, bhms_call *call)` | Arguments are decoded and already inside the local limits. Return `BHMS_RUN_DONE` (fill `call->results`, `call->evidence`), `BHMS_RUN_STARTED` (finish later with `bhms_op_finish`), `BHMS_RUN_FAILED` (`call->fault`) or `BHMS_RUN_REJECTED` (not started; `call->error`, default `PRECONDITION`). |
| `uint8_t cancel(user, handle)` | `BHMS_CANCEL_CONFIRMED` (ended now), `_ACK` (will finish via `bhms_op_finish`), `_REFUSED`. NULL refuses. |
| `uint8_t read(user, fresh, bhms_value *out, bhms_sample *meta)` | Return a `BHMS_Q_*` quality; no value is sent for invalid/unknown (CMP-060). |
| `uint8_t stop(user, reason, uint8_t *evidence)` | Make the device safe. `BHMS_STOPACK_CONFIRMED` or `_INITIATED` (then call `bhms_stop_confirmed`). NULL device stop => `STOP_SUPPORTED` clear. |

Field limits are in wire units (`BHMS_U16_RANGE(0, 1000)` for a `u16` field with
`scale 0.1` means 0.0 to 100.0). Application calls: `bhms_op_finish`,
`bhms_op_progress`, `bhms_publish` (unsolicited VALUE), `bhms_stop_confirmed`,
`bhms_set_inhibit`. The description sidecar JSON (with `compact` layouts) must
use the same indices, types and scales; `tools/bhms_digest.py sidecar.json --check`
validates it against the BHMS device model and prints the `digest8` initialiser;
`--header out.h` writes `#define BHMS_DIGEST8 {...}` for the firmware to `#include`
(the example's `led_analog_digest.h`; a test keeps it equal to the sidecar).
An integer wire field without `scale` needs a `type: integer` (or `multipleOf: 1`)
schema in the sidecar (BHMS-DEV-071).

Thread-safety: single owner. Call every `bhms_*` function from one context; none
is interrupt-safe.

## HAL (`include/bhms_hal.h`) -- what Task 13b ports to RP2040

| Hook | Notes |
|---|---|
| `uart_read(ctx)` | next byte or -1; non-blocking |
| `uart_write(ctx, buf, n)` | may block |
| `millis(ctx)` | free-running ms counter |
| `stop_pin(ctx)` | optional; nonzero while the stop input is asserted |
| `epoch_load/epoch_store(ctx, ...)` | optional pair: the persistent boot counter (EEPROM/flash); erased reads as 0; `store` returns 0 only when durable. Without them `PERSISTENT_EPOCH` is not advertised. |

The Arduino wrapper (`arduino/BHMS/src/BHMSDevice.h`) maps these onto a `Stream`,
`EEPROM` (4 bytes at a configurable address), `millis()` and a digital pin.
`examples/LedAnalog` is the acceptance sketch (LED action, analog-read property).
The wrapper header is `BHMSDevice.h`, not `BHMS.h`, to avoid clashing with
`bhms.h` on case-insensitive filesystems. `library.properties` has no `url` yet and lists only the `avr` architecture until
Task 13b supplies and tests an RP2040 HAL.

## Build and test

```sh
cmake -S sdk/c -B build -DCMAKE_BUILD_TYPE=Debug   # ASan+UBSan on by default
cmake --build build && ctest --test-dir build --output-on-failure
```

* `test_codec`: spec 11.10 vectors byte for byte, every layout, stuffing round trip.
* `test_endpoint`: state machine over the in-memory HAL (epochs, replay ring,
  conflicts, session checks, fences, TTL, BUSY, async/cancel, stop, stop pin,
  NEW_SESSION, corruption, oversize, bounded polling, init validation).
* `e2e_native_pty`: `tests/host/test_e2e.py` drives the native `sim_device` over
  a pty; the harness (`tests/host/bhms_host.py`) is an independent struct-based
  implementation of the layouts using `protocol/serial/frame.py`.
* `description_mirror`: BHMS-DEV-071 mirroring of the example sidecar and the canonical
  spec example, and the generated digest header.
* `arduino_library_in_sync`: the Arduino copies equal the sources
  (`scripts/sync_arduino.sh` regenerates them).

AVR target (Docker on the lab worker; the toolchain is not installed locally):

```sh
sdk/c/scripts/run_avr_on_worker.sh      # ships sdk/c to ~/hms-lab, builds the image,
                                        # builds 328P/2560, runs the e2e in simavr
```

`scripts/avr_build.sh` builds the example for ATmega328P and ATmega2560 and
writes `sizes.txt`; `scripts/avr_sim_test.sh` builds `tests/simavr/runner.c`
(libsimavr, UART0 on stdin/stdout, LED pin events on stderr, EEPROM persisted to
a file) and runs the same `test_e2e.py` against the firmware.

## Limits

* One `bhms_endpoint` per UART; `BHMS_MAX_ACTIVE` operations at a time (default 2).
* Argument and result blocks are bounded by `BHMS_MAX_ARGS`/`BHMS_MAX_RESULT`
  (default 16); `bhms_init` rejects a table that exceeds them. The protocol
  allows 182 bytes; raise the macros if needed (RAM grows by ring size times it).
* `bhms_poll` runs callbacks inline and writes replies synchronously; a slow
  callback delays the link by its duration. A 64-byte UART RX buffer fills in about
  5.5 ms at 115200 baud, so any callback (or other main-loop work between polls)
  longer than about 5 ms drops bytes, possibly a STOP frame. Such actions must
  return `BHMS_RUN_STARTED` and do their work from the main loop in small steps.
* The hardware stop input must be latched by the HAL (pin-change ISR or capture)
  and held until read once; a pulse that arrives while a callback is running would
  otherwise be lost. The Arduino wrapper does this on interrupt-capable pins
  (Uno: 2 and 3); other pins are level-polled only.
* `bhms_init` failure (table exceeds the bounds, missing HAL hook) leaves the
  endpoint inert: `bhms_poll` and the application calls do nothing. Check the
  return value; the example sketch blinks the LED fast and halts.
* `PERSISTENT_EPOCH` is advertised only if the stored counter was read and the new
  value stored; the stored read-back in the Arduino wrapper makes AVR EEPROM
  durable. Other cores whose `EEPROM.put` is RAM-only until a commit need a
  HAL that commits, which is why `library.properties` lists only `avr`.
