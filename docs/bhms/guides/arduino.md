# Arduino and other microcontrollers

This guide shows how to make a small microcontroller (ATmega328P class and up) a BHMS device: the C library and its
Arduino wrapper speak the compact binary binding over the serial line, and a gateway serves the board to clients and
agents as an ordinary device. It walks through the example sketch, the description sidecar, flashing, the gateway
configuration, and a complete run without a board (the library's host build behind a real gateway), which the docs test
executes. The binding is [spec 11](../../../spec/bhms/11-compact-binding.md); the library is
[`sdk/c`](../../../sdk/c/README.md).

## How it fits together

```text no-run
 client / agent ──JSON-RPC──> gateway ──HM frames over UART / USB CDC──> board (sdk/c endpoint)
                              │ holds the full description (sidecar JSON)      │ keeps its action table, local limits,
                              │ keeps the durable operation journal            │ fence floor, replay ring, boot epoch
                              │ does all JSON-RPC work                         │ and stop procedure
```

The board cannot describe itself in JSON. It reports, in its `HELLO`, the first 8 bytes (`digest8`) of the digest of its
description; the gateway holds that description as a **sidecar** file and serves the board only when the digests match.
A board that was reflashed with different tables is never served under the old description.

## The example sketch

[`sdk/c/arduino/BHMS/examples/LedAnalog`](../../../sdk/c/arduino/BHMS/examples/LedAnalog/LedAnalog.ino) has one action
(`led_set`: switch the LED, return how many times it was written) and one property (`analog0`: the raw A0 reading). The
tables are in flash; index in the table is the `compact.index` in the sidecar:

```c no-run
BHMS_FIELDS(ledIn) = {BHMS_BOOL()};                       // argument layout of led_set
BHMS_FIELDS(ledOut) = {BHMS_U8()};                        // result layout
static const bhms_action actions[] BHMS_PROGMEM = {
    BHMS_ACTION(ledRun, 0, 0, BHMS_FIELDS_REF(ledIn), BHMS_FIELDS_REF(ledOut))};
static const bhms_property props[] BHMS_PROGMEM = {BHMS_PROPERTY(adcRead, BHMS_U16)};
static const bhms_device dev = {BHMS_DIGEST8, 0, actions, 1, props, 1, 0, 0};
BHMSDevice bhms(Serial, dev);

void setup() { pinMode(LED_BUILTIN, OUTPUT); Serial.begin(115200); if (bhms.begin() != BHMS_OK) for (;;) {} }
void loop() { bhms.poll(); }                              // drain the UART, run frames, watch the stop pin
```

Callbacks run inline from `poll()` and must be short: a 64-byte UART buffer fills in about 5.5 ms at 115200 baud, so
anything longer returns `BHMS_RUN_STARTED` and finishes from the main loop with `bhms_op_finish` (see the
[library README](../../../sdk/c/README.md#limits) for the limits, the stop input and the persistent boot epoch).

## The sidecar

The sidecar is a full `DeviceDescription` whose actions and properties carry `compact` layouts (index, wire types,
scales). The digest tool validates it against the device model and prints the `digest8` the firmware must report;
`--header` writes it as `led_analog_digest.h` for the sketch to include:

```sh run
python sdk/c/tools/bhms_digest.py sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json --check
python sdk/c/tools/bhms_digest.py sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json --header digest.h
cat digest.h
```

```text output
sha256:238ae39cebf1188c...
#define BHMS_DIGEST8 {0x23, 0x8a, 0xe3, 0x9c, 0xeb, 0xf1, 0x18, 0x8c}
```

Change a table, change the sidecar, regenerate the header, reflash: the three must agree, and the gateway refuses a board
whose `digest8` differs from its sidecar. Integer wire fields without a `scale` need an integer schema
(`"type": "integer"` or `"multipleOf": 1`); scaled fields are in wire units on the board and in physical units in the
description (`u16` with `scale 0.1` holds 0.0 to 100.0).

## Flash a board

Not run by the docs test (it needs a board and the Arduino toolchain). Install the library by copying
`sdk/c/arduino/BHMS` into your Arduino libraries folder, then build and upload the example, for example with
`arduino-cli`:

```sh no-run
cp -r sdk/c/arduino/BHMS ~/Arduino/libraries/
arduino-cli compile --fqbn arduino:avr:uno ~/Arduino/libraries/BHMS/examples/LedAnalog
arduino-cli upload  --fqbn arduino:avr:uno -p /dev/ttyACM0 ~/Arduino/libraries/BHMS/examples/LedAnalog
```

The library lists only the `avr` architecture until a HAL with a durable boot counter is tested for other cores (the
BHMS Arm's RP2040 port is in [`hardware/actuator/firmware`](../../../hardware/actuator/firmware/README.md)).

## Serve the board through a gateway

A `type = "compact"` upstream is a bridge inside the gateway: it opens the serial port, says HELLO, checks the digest and
serves the board as `<name>/<deviceId>`. The repository's
[`examples/bhms/compact-gateway.toml`](../../../examples/bhms/compact-gateway.toml) serves this board and the BHMS Arm
(not run by the docs test: it opens `/dev/ttyACM0`):

```toml no-run
[[upstream]]
name = "led"
type = "compact"
port = "/dev/ttyACM0"            # USB CDC / UART; pty:/dev/pts/N or unix:<path> for simulators; never a network link
baud = 115200
sidecar = "../../sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json"
```

The serial line must be exclusively owned: the frame check detects corruption, not forgery, so a networked link
(`tcp://`) is refused at start-up (BHMS-SEC-050). Link timing (`reply_timeout_ms`, `retries`, `poll_interval_ms`,
`probe_interval_ms`, `hello_timeout_ms`) is in the [gateway configuration reference](../reference/gateway-config.md).

## Try it without a board

The library builds for the host too: `sim_device` is the LedAnalog endpoint (the same C endpoint, on stdin/stdout instead
of a UART, with a file as its persistent boot counter). Build it:

```sh run requires=cmake timeout=300
cmake -S sdk/c -B build-c -DCMAKE_BUILD_TYPE=Debug -DBHMS_BUILD_TESTS=OFF > /dev/null
cmake --build build-c --target sim_device > /dev/null
ls build-c/sim_device
```

Serve it on a Unix socket as if it were a serial port. `python -m bhms.testing.compact_endpoint` (an SDK test aid)
starts the process, gives it a persistent boot counter in its work directory, and carries the frames between it and
whoever connects:

```sh run background wait=board.sock requires=cmake
python -m bhms.testing.compact_endpoint build-c/sim_device board.sock --workdir board-work
```

The gateway configuration differs from the hardware one only in `port`. Save as `board-gateway.toml`:

```toml file=board-gateway.toml
[gateway]
id = "board-gw"
state_dir = "board-gw-state"                 # the bridge's journal goes to board-gw-state/compact/led.sqlite3
listen = ["unix:board-gw.sock"]

[[upstream]]
name = "led"
type = "compact"
port = "unix:board.sock"
sidecar = "sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json"
```

```sh run background wait=board-gw.sock requires=cmake
bhms gateway board-gateway.toml
```

Clients see an ordinary device, described by the sidecar; invokes become compact frames, and the board's answers become
operations in the gateway's journal:

```sh run requires=cmake
bhms ls unix:board-gw.sock
bhms describe unix:board-gw.sock led/bench-led
bhms call unix:board-gw.sock led/bench-led led_set on=true --key led-on-1
bhms call unix:board-gw.sock led/bench-led led_set on=true --key led-on-1
bhms read unix:board-gw.sock led/bench-led analog0
```

```text output
led/bench-led Bench LED board online bhms.io.gpio led_set analog0
action led_set(on: boolean) effect=reversible repeat=idempotent lease=no cancel=no evidence=reported max=100ms -> {writes: integer}
property analog0: integer measured
led/bench-led.led_set op-... completed: writes 1 (effect unverified, ...)
led/bench-led.led_set op-... replayed: completed writes 1 (effect unverified, ...)
led/bench-led.analog0 = ... (measured, valid, age unknown)
```

The second call with the same key is answered from the gateway's journal and never reaches the board: `writes` is still
1. The reading's age is unknown because this endpoint reports no bounded acquisition latency, and a reading of unknown
age fails every freshness requirement rather than passing as recent (BHMS-OBS-003):

```sh run requires=cmake exit=1
bhms read unix:board-gw.sock led/bench-led analog0 --max-age-ms 500
```

```text output
Refused: bench-led.analog0: the age of the newest observation is unknown ...
```
 If the board resets while an operation is in flight, the gateway marks that operation `unknown` and does not re-send
it; only a persistent boot epoch that advanced (or a new session the board accepted) proves the old work was purged.

## Writing your own firmware

- Start from `include/bhms.h` (API, wire constants) and `include/bhms_hal.h` (the HAL a port implements: UART read and
  write, a millisecond clock, an optional stop pin, an optional persistent epoch store).
- Keep limits on the board: arguments arrive decoded and already checked against the layout's local limits
  (`BHMS_U16_RANGE(...)`), and the board refuses what it cannot do (`BHMS_RUN_REJECTED`) before acting.
- Report evidence honestly in `call->evidence`: `measured` only from a sensor, not from having driven a pin.
- Implement the stop callback for anything that moves, and latch the hardware stop input in an interrupt.
- Prove it: the host build runs the library's own tests (`ctest`, with AddressSanitizer and UndefinedBehaviorSanitizer),
  and `bhms conformance compact-gateway` runs the compact profile against the reference endpoints
  ([running conformance](conformance.md)).
