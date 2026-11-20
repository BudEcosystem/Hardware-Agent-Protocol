# Combined qualification preflight: 61 pure tests pass

All **61 selected methods passed**: 31 inherited domain/timing tests and 30 new
combined-matrix tests. Test time was **11.494 seconds**, with **18.022 seconds**
including the harness, within the original 180-second deadline. These tests
generate and validate plans; they do not execute the planned qualification trials.

[Proof](proof.json) verifies all 7,062 inherited project/data files remain
unchanged, with stable inventories of 7,064 project files, 7,067 frozen preparation
entries, six active harness files and 159 selected external pins. All 689 origins
match; 208 bytecode reads are refused, with no recorded prohibited attempts.
Compiler/driver receipts match within the invocation. The complete attempt and
original empty private scratch root remain retained.

The new planner preserves candidate nominal/boundary/negative cases, attaches
exact replay and changed-same-key probes to successful candidate executions, and
adds all 25 named fixed challenges. Controlled timing artifacts remain distinct
from the candidate. The resource challenge declares four actors, both primitives,
shared GPIO/PWM and cross-route exclusion, independent-pad progress, exact replay,
and historical receipt reads while a later alias owns the same pad.

All cases, child-operation ceilings and tick reservations count globally before
execution. A constant one-step candidate requires 30 cases, 42 child-operation
reservations and 1,676 ticks. A sixteen-step constant candidate requires 57 child
reservations and 1,736 ticks. The ordinary duration-parameter example requires
37 total cases and is refused under the original 32-case ceiling. This is an
exposed capacity limitation, not permission to omit coverage or redefine the
end-to-end goal around constant applications.

Tests reject missing/extra actors, mismatched sessions, wrong shared claims,
same-route aliases, unselected targets, widened or mistyped limits, understated
totals, omitted/reordered cases, modified effects and invented success flags.
Opaque action names and explicit cross-route role swaps preserve the trusted
primitive mapping. Exact regeneration checks the entire plan. Returned data
cannot mutate cached topology; planning and validation remain pure after trusted
construction.

Actual scenario execution, expected-outcome reduction, byte/record/wall-budget
enforcement, current-source attestation and hard aggregate storage remain required.
The plan names the missing worker capabilities, including auxiliary actors,
same-key conflict capture, in-phase guard delays, clock fault/new-epoch history,
binding changes and full read withdrawal. No qualification success is claimed.
No Runtime, SQL connection, physical device, MCU/emulator, inference or public
service ran. Live HMS and the adjacent Harness remain unchanged. Primary-agent
review only; independent helpers remain unavailable.
