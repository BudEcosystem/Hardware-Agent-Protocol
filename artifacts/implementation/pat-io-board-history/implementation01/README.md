# Independent GPIO/PWM board-history component

This isolated candidate adds a pure semantic checker and 35 tests over the exact
trial20 data already used by the transcript reader. All 2,800 inherited project
and fixture files remain unchanged. The intended combined selection contains the
39 reader methods plus these 35 semantic methods on one 2,802-file closure.
Preparation is static only; actual execution and any failures are retained later.

The checker imports shared canonical/invocation parsing, the independent transcript
reader and pure topology/proof contracts. It imports no worker, board, adapter,
installation provider or provider state validator. After module setup it performs
no filesystem, clock, SQLite or device calls. Separately trusted setup associates
the historical transcript with its intended installation; historical identities
are not reconstructed or qualified as the current source closure.

The checker independently derives GPIO/PWM footprints from typed access,
pin/timer/channel and atom relations, compares alias expansion with that footprint,
and derives active/idle states from exact integer arguments. Complete resource and
instance inventories include unrelated pads and aliases. It checks metadata,
scoped proof documents, operation intent digests, dispatch/attempt/event joins,
receipt identities, immutable predecessor versions and authority receipt copies.
Receipt histories must be append-only. Current rows must equal their latest
versions. Counters are recomputed from every operation's retained history; a
balanced but invented count is insufficient. Pending owners/claims, persistent
fences, chronological fence increases and actual modeled resource states must
agree, including when an older terminal receipt shares a pad with a newer owner.

First captured effect transitions must occur within retained adapter/cycle phases
or the declared reopen cancellation phase. Starts and completions are checked
against recorded clocks, duration/run windows, completion limits and admission
leases. The four supported cancellation causes are checked against captured
state/timing: client cancellation, owner reopen, execution deadline and lease
expiry. Provider completion may precede authority settlement; that cut remains
valid and reports the raw authority state/claim count at first capture.

Tests expect eighteen coherent actual histories with 29 activations, 26 completed
cycles and three canceled activations. The deliberately missing current receipt
must refuse without repairing or discarding its evidence. The data-only adversarial
writer rebuilds typed pages, row counts, ordering, references and hashes. Every
semantic mutation must first pass the independent structural reader, then fail
the intended history check. Inner receipt/dispatch/proof hashes are recomputed
where relevant. A purity check vetoes file/clock/database access during inspection.

This is a semantic component, not the full outcome reducer. It checks one declared
PAT actor; auxiliary challenge actors still need an explicit trusted manifest.
No-start guard-cause attestation and other authority/clock-loss causes refuse as
unsupported here. Full operation/event/procedure/replay/floor semantics, intent
correspondence to independently lowered PAT parameters, complete live configuration
attestation, final settlement and matrix/fault qualification remain unfinished.
`boardHistoryChecked` describes modeled history only; authority and independent
outcome flags, and `qualificationPassed`, remain false. Physical electrical
behavior, autonomous stopping, hub control and persistent applications are not
established by this component.

No live HMS runtime, earlier frozen artifact, adjacent Harness checkout or actual
device is changed. Helper account limits prevent independent agent review; the
source review is by the primary agent only.
