# Retained-prefix audit plan

Status: auditor source prepared, not executed. This audit never imports candidate
modules, compiles, launches or signals a process. Its only write is a new exclusive
`AUDIT.json`; all SQLite connections use URI`mode=ro&immutable=1` and`query_only=ON`,
and each DB is hashed before and after the read.

The actual matrix stopped at the mutation profile's unchanged30-second wall
limit. Negative passed8 cases/136 checks; storage passed10 cases/122 checks.
Their completed-case checks sum252, with six additional owner/finalization checks.
The failed mutation profile retained209 partial checks and no completed case.
It independently recorded one clean native reap despite the outer reducer's
`innerReaps:0` field, which means the reducer had not loaded the inner result.
The audit must join19 actual native reaps plus3 outer reaps:22 identities.

`AUDIT-INPUT-PINS.json` binds exactly995 files in the three original attempts:
337 negative,343 storage and315 mutation. Its SHA256 is
`d2c1e0432dc5da5e1d63cc022e01b212b7c33b1d41b17cd3cdcc375a161568a3`.
It was prepared by hashing retained files as data, not by running the auditor.
Both sealed parent indexes,4530 indexed parent files, public244, all260 reuse
pairs and20 provenance pairs are checked independently. Every frozen source byte
and all306 review entries join the original manifest and each actual command.
The original native image, qualifier executable, absolute argv, reservation,
receipt and original12/638 stdout remain pinned; there is no qualification rerun.

For each completed case the auditor joins its actual start handle, expected clean
exit/reap and exact ordered membership in the inner records. It checks all28
native snapshot selectors, exact per-case state/record/driver-count expectations,
canonical deployment/outbox/activation/episode/conflict bytes, original-key/wire
identities, shared physical2/actual3 claims and installed source/image/interpreter
binding. Raw stream request/response association is checked separately from
bounded retained contradictory packets. An overflowing17th contradiction is
explicitly distinguished from the original16 retained packets.

Logical accounting is recomputed independently in Python from retained SQLite
cells, not by importing the production checker or repeating its SQL expression.
This covers the observed databases only; no16MiB saturation or unexecuted capacity
control is inferred. Every completed original effect body is handed off once,
and an abandoned/never-possible OPEN has no matching effect send in the trace.

The failed DB is audited separately:68 retained canonical`never_handed_off` START
identities, keys`never-start:0..67`, endpoint sequence1, accepted OPEN with current
mutation sequence0, no activation rows, and all three original claims retained.
Each settlement has its unchanged-sequence STATUS receipt. There is no completed
native counter snapshot or raw trace file for this failed case; neither is
reconstructed or invented. Its stack and TERM cleanup explain where the observed
bound interrupted the living owner, not a general performance proof.

An auditor pass means these retained facts are consistent. It must still report
the mutation profile failed, five later profiles unexecuted,24-case matrix false,
simultaneous maximum histories unestablished and physical/protected/public
eligibility false. The old failure remains failed under any later proposal.
