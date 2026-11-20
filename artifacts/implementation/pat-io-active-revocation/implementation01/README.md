# Active permission-withdrawal capture trials

This candidate adds six original private-runtime tests while preserving all
5,050 inherited project/data files. It uses the already implemented trial engine,
configuration capture and synthetic GPIO/PWM provider without production edits.
The closed selection contains the prior 32 capture tests plus these six cases.

The tests withdraw the active actor's invocation permission by granting explicit
read permission and removing the original wildcard administrator grant. Read
permission remains so actor status remains observable. A separately declared test
plan pins the grant-change phase and is retained alongside each new manifest.
The captured grant rows are not used to generate that plan.

Cases cover active GPIO stopping with a remaining PAT step, shared PWM output
restoration, revocation exactly at the modeled due time, completed-effect
reconciliation after authority reply loss and subsequent revocation, committed
revocation-stop reconciliation after reply loss, and precedence of an already
requested cancellation. Expected raw counters distinguish five canceled
activations and one completed activation. Stop proof and authority claim release
are asserted separately. No regrant, new replay key, reset or fabricated idle.

All streams share the existing 4,096-record/16 MiB/64 KiB-document limits,
2,048 ticks and 60-second cooperative trial boundary. The inherited integration
harness keeps 600 seconds and 64 MiB raw retention. Original scratch, failed
partial output and all copied state are retained. Production code and all previous
tests remain unchanged. No physical device, MCU/emulator, live inference, public
service or acquired research/controller code is executed.

This stage captures actual original-host behavior. The current independent
configuration checker explicitly refuses active revocation, and the board checker
cannot yet attest the broad authority_or_binding_lost cause. Independent guard
cause/outcome composition and the wider fault matrix remain required. All full
configuration-attestation, independent-outcome and qualification flags stay false.
No live HMS or adjacent Harness changes. Primary-agent review only; helper account
limits prevent independent review. Actual execution results remain separate.
