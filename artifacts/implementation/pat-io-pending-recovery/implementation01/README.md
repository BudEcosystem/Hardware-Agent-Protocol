# Pending-output recovery capture

This isolated candidate adds eight actual private-runtime fault trials to the
prior 38 capture methods. All 5,903 inherited project/data inputs remain exactly
unchanged, including production runtime/provider/compiler and independent readers.
One new test file yields 5,904 project/data inputs. No live HMS changes.

The named trusted schedules inject a lost board-begin reply after activation,
a board-finish failure before commitment, or an authority-reconciliation failure
after the board stop has committed. Schedules are declared separately from raw
state and retained with each manifest. Injection call counts and phases are
asserted; the harness checks the exact reviewed schedule map without importing
test code. Authority plans separately specify unchanged administration or the one
invocation-withdrawal phase with retained read authority.

Cases cover GPIO with an unstarted remaining PAT step, all three PWM resources,
a failed pending finish, recovery at due time, invocation withdrawal, prior
cancellation, a committed stop with lost authority reconciliation, and a failed
recovery stop followed by recovery. Unknown authority state does not imply idle.
Pending receipts retain their activation, output state, ownership and claims.
Recovery uses the existing same operation and receipt, stops to modeled idle,
then reconciles and releases authority claims. The intended eight final receipts
are canceled with reconciliation_stop; no new activation or completed cycle is
expected. A prior canceled parent remains canceled even when the child's recovery
settles as failed; that is distinct from a confirmed client-cancel stop cause.

Original streams retain 4,096 combined records/16 MiB/64 KiB documents, 2,048 ticks
and 60-second trial limits. The inherited runtime harness retains 600 seconds and
64 MiB raw scratch, with no enlarged bounds. Original scratch and partial/failed
outputs are retained. No reset, replacement operation key or regrant is used.
No physical port/device, MCU/emulator, live inference, public service or acquired
controller executes. This stage captures actual host simulation behavior; the
existing composed reader still refuses pending-unknown recovery. Independent
trusted-fault/cause checking, broader fault/auxiliary-actor coverage, current
compiler identity, enforced aggregate storage and qualification remain unfinished.
All full-outcome/qualification flags stay false. Primary-agent review only;
helper account usage limits prevent independent review. Results are separate.
