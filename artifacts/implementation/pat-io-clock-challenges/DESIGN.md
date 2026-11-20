# Retained clock controls and new-epoch recovery

Continue the closed combined matrix with all three remaining clock/guard cases
on both installed primitives. Preserve the exact candidate and challenge plans,
original effect/operation budgets, private runtime state and every failure.

The old recorder equates wall and monotonic clocks and assumes time is constant
inside a phase. Add two default-preserving clock hooks and an opt-in 0.3 capture
profile. The new subclass owns separate wall and monotonic sources. Its only
controls are the three fixed matrix schedules; it accepts no arbitrary callback,
time list or production device access.

The start/run boundary advances both sources by 99 ms after a dispatch link is
reserved and before the actual board begin/guard. The one-millisecond requested
cycle would end exactly at the original 100 ms run limit. The existing provider
must retain start-excluded evidence without activation or a board fence.

The wall case regresses only wall time by one millisecond while output is pending.
The mapping case regresses only monotonic time and exercises the existing sticky
mapping-invalid latch. Restoring that source under the same owner must still
refuse. The phase engine's forced refresh can fail before adapter progress; this
does not establish autonomous bounded stopping. Retain active output/claims at
that checkpoint. Recovery closes and reopens the same databases at a source time
above the retained floor, creating owner epoch 2 and a new board session. It must
retain the old request, operation, receipt and floors, reconcile the historical
stop, refuse resumption of unresolved dependencies, and cancel the parent without
admitting its suffix. No invalid-state deletion or old-owner latch clearing.

The pure opt-in reader validates the new clock grammar, exact named control/call
schedule and paired configuration serialization. It rejects old-reader use and
rehashed control/case alterations. This stage does not yet compose semantic
board/authority/parent/sample folds over regressed clocks and in-phase time.
Full-history, expected-response and qualification flags remain false. Actual
runtime assertions and retained raw data supply the input for that next step;
they do not substitute for independent outcome evaluation or group qualification.

Run seven new methods plus 39 unchanged transcript methods in one selection, and
the four existing configured runtime methods separately. Keep 180 seconds,
16 MiB scratch and all existing acquisition/origin limits per invocation.
Review/freeze source and exact harness diffs before execution. Only original
host SQLite simulations run; no live services, inference, acquired controllers,
physical ports, target binaries or adjacent Harness edits.
