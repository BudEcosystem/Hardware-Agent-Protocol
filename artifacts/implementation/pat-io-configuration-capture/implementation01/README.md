# Configuration capture for finite I/O trials

This candidate adds a configuration stream to the original private IoRuntime
trial engine. Each snapshot references an exact execution checkpoint, captured
while both authority and shared-board locks remain held with no open transaction.
A no-op binding hook is the only inherited source change. It lets the subclass
retain the actual resolver registration and its identity on every runtime open.
All 2,807 other inherited project/data files remain byte-identical.

Fifteen registry tables retain types, instances, capabilities, bindings and their
history, presence, endpoint sessions and history, observations, streams and their
history, grants and resource requirements. Registry metadata deliberately projects
only deployment, revision and version. Cursor signing material remains in the
private retained raw database and is excluded from the JSON evidence streams.

Typed ordered eight-row pages and resolver records are reused by content hash.
Every configuration and legacy record consumes the SAME original 4,096-record
and 16 MiB limits, with 64 KiB documents, 2,048 ticks and 60 seconds per engine.
No effect or protocol bound changes. Failures preserve partial raw output.

The selected 32 original host tests contain the prior 20 engine tests plus 12
configuration tests: GPIO and PWM execution, reopen/session changes, permission
withdrawal before parent admission and before child dispatch, shared record/byte
limits, page reuse, transaction refusal, held locks/read-only capture, secret
exclusion and registration identity, and a full sixteen-step execution. One new
GPIO trial also passes the five existing independent semantic readers after its
final capture. Those readers do not attest the configuration stream.

This component is a producer, not an independent authorization attestor. Every
configuration, full-outcome and qualification flag remains false. New grants
fixtures exceed existing semantic-reader coverage and are retained for future
work. No live source, physical device, model, public service or adjacent Harness
is changed or executed. Primary-agent static review only; helper account limits
prevent independent review. Actual test results are retained separately.
