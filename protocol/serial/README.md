# Experimental serial framing

This is an original Python encoder/decoder and portable C decoder for the [constrained binding draft](../../spec/07-constrained-binding.md). It has no UART driver, operation admission, replay protection, authentication, procedure executor or device callback. Decoded frames are untrusted application input until those layers validate them.

Run the cross-language fixtures and native memory checks:

```sh
python3 -m unittest discover -s tests -p 'test_serial_frame.py' -v
python3 scripts/check_serial_native.py
```

The tests compile `frame.c` with native GCC and compare wire behavior to Python. The second command uses AddressSanitizer/UndefinedBehaviorSanitizer and records the compiler, exact source hashes and synthetic workload in [the verification artifact](../../artifacts/verification/serial-frame.json). Neither command opens a serial port or runs acquired research code. Python 3, GCC and the existing description-test dependencies are required; dependencies are not yet locked for a release.

The C parser owns a fixed 214-byte decoded buffer. A completed frame's raw bytes remain available only until the next feed/reset. Its `length` member is receive-state bookkeeping, reset at a flag; derive completed length from the validated payload-length header. One caller must supply bounded event handling and an absolute receive deadline, and reset on UART errors/link changes. Do not use the parser concurrently or queue pointers into its mutable buffer.

The measured host parser structure is 220 bytes. An [ATmega328P build](../../artifacts/verification/serial-avr.json) measures 219 bytes for the parser, and 558 bytes flash/221 bytes static RAM for its minimal build-only harness plus startup. This excludes UART, application/authority logic and total stack. [Build instructions and core review](../../research/constrained/avr/notes/target-build-and-uart-review.md) explain the isolated toolchain and stock Serial error-notification gap. Target execution, RTOS builds, UART integration, session/authority protocols, timing and hardware fault tests remain required.

[Independent review](../../artifacts/verification/serial-review.json) found no substantive framing defects in its stated scope. Historical review hashes are retained separately from the current test artifact.
