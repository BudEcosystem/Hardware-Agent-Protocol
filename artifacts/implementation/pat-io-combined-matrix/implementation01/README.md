# Closed combined I/O qualification preflight

This candidate adds a pure combined planner and exact plan validator. It preserves
the existing candidate nominal/boundary/negative matrix, attaches exact replay and
changed-same-key probes to successful candidate trials, and adds all 25 named
provider/authority challenges. No caller-provided fault list, callback, command,
success flag or arbitrary test implementation is accepted.

Candidate artifacts remain unchanged. Fixed challenge artifacts are separately
identified, whole-domain checked programs with controlled windows, required for
testing boundary precedence independently of a candidate's own timing. Offsets
are relative to the trial origin. Before advancing to a start boundary, admit the
first child and hold dispatch; an `at` field identifies the exact interruption
point. Two-step challenges reserve a suffix and require that it never runs after
the first interrupted child. Named clock/binding/grant changes require separately
retained trusted change evidence. They are requirements for a future worker, not
proof that the existing phase engine can execute them.

The 24 single-target challenges cover accepted/pending cancellation and reopen,
lost completion/pending replies, lower/start/run/wall/lease timing, delayed parent
reporting, clock regression/mapping loss, four permission boundaries plus complete
read withdrawal, and binding invalidation before/after activation. The resource
challenge declares four actors: shared GPIO, PWM, a cross-route GPIO alias and an
independent pad. It executes four explicit admitted operations and records the
busy contenders, exact replays and historical receipt read while a later alias
owns the pad. Both primitive directions are tested. These are policy challenges,
not hidden candidate steps.

Trusted challenge bindings must match the exact normalized installation, semantic
units and expected primitive mapping. The selected candidate is the declared GPIO
or PWM target. Distinct actor identities, one board session, exact shared claims,
different alias routes and disjoint independent resources are required. Opaque
action names and an explicitly swapped cross-route target are supported.

All candidate and challenge cases, admitted-child ceilings and tick reservations
share the original 32-case, 512-operation and 2,048-tick ceilings. The original
16 MiB producer evidence, 4,096 records, 64 KiB documents, 20 MiB derived closure
and 60-second group wall limit remain unchanged. Configuration may lower them.
The serialized plan obeys document/derived limits. Actual output/storage/deadline
enforcement remains a required worker/service feature; planning is not evidence
that every execution will fit those bounds.

A constant one-step candidate plans 30 cases, 42 child-operation reservations and
1,676 ticks. The ordinary duration-parameter example requires 37 cases and is
refused under the original ceiling. The planner does not omit negative/fault
coverage to fit it. This exposes a design capacity limit; it does not redefine
the full goal as literal-only applications or authorize wider execution bounds.

Exact validation regenerates the complete plan and checks all cases, ordering,
artifacts, binding identities, expectations, totals, limits and required features.
Returned data is detached from internal topology state. Plans report no execution,
verified outcomes, implementation attestation, aggregate storage enforcement or
qualification success.

All 7,062 inherited project/data files are unchanged. The validation selection is
31 inherited timing/domain methods plus 30 new matrix methods. Pure planning tests
do not run any listed challenge. No Runtime, SQL connection, physical device,
MCU/emulator, inference, public service or acquired controller runs. Primary-agent
review only; helpers remain usage-limited. Live HMS and the adjacent Harness are
unchanged. Actual test results are retained separately.
