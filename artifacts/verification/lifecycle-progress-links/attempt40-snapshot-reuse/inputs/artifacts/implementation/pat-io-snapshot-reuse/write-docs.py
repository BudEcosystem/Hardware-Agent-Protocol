"""Reconcile complete current groups and the actual remaining qualification gates."""
from pathlib import Path
ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'
assert not (B / 'results/index.json').exists()

path = ROOT / 'PROGRESS.md'; text = path.read_text()
assert text.count('The current [page-encoding stage]') == 1
text = text.replace('The current [page-encoding stage]', 'The preceding [page-encoding stage]')
anchor = 'The separate [qualification supervisor rebase]'; assert text.count(anchor) == 1
text = text.replace(anchor, '''The current [snapshot-reuse stage](artifacts/implementation/pat-io-snapshot-reuse/results/README.md)
passes **132 distinct methods**, including **complete fresh GPIO and PWM capture
with independent group inspection**. Each uses one constant single-step candidate,
its negative cases and all 25 fixed challenges: 30 cases per group. The reader
matches separate pre-run setup, derives expected outcomes and checks exact archive
closure/accounting. File, SQL and clock access are forbidden during inspection;
dispatch counts are 8 timing, 3 clock, 10 lifecycle, 3 authority and 1 resource
challenge. Three early forged-archive variants refuse in each full pipeline.

The existing eight-entry schema memo now retains immutable bounded snapshots.
Warm canonical bytes can reuse a validated snapshot; objects still undergo
canonical bounds and original-type checks before lookup. Every result is detached
without caller copy hooks. Graph, footprint, generation, binding and source checks
remain; no mutable authority result is cached. Installation normalization reuses
its first encoding after the original float scan. Source comparisons retain all
SQL/capture/writer/budget modules and graph/generation/source semantic functions.

The first pure129 attempt has 128 passes and one new assertion failure: it counted
two graph checks while alias closure supplies a third. Source02 changes only that
assertion to require the exact three graph checks. The corrected 129 methods pass
in 37.369 test seconds, and the actual record cutoff passes in 4.640 seconds with
the same 977,425 raw bytes as before. All previous failures remain retained.

GPIO and PWM full test runs pass in 65.224/65.659 seconds, including pre-run setup,
capture, independent inspection and adversarial checks. The original 60s capture
guards, 180s parent deadline and all storage/effect/case ceilings remain. These
single-run results are not performance benchmarks or wall-time attestation.
Each group verifies 28 operations, 44 reserved admissions, 99 ticks and 3,832
worker records. GPIO/PWM derived bytes are 14,660,708/14,875,180. Their 30 case
inspection documents total 216,187/217,881 bytes; each complete inspection output
contains 32 files. Each retains 26 states/52 databases, with 21 activations,
11 completions, 10 cancellations and zero endpoint claims/owners. Read-only
integrity checks and hashes pass. Raw scratch totals 15,333,173/15,575,194 bytes.

All five attempts retain 228 project/231 frozen inputs, six active harness inputs,
159 external pins, matched origins and unchanged within-attempt identities. The
original failed129 and all raw output/copies remain. Primary-agent review only;
helpers remain usage-limited. Live HMS and the adjacent Harness are unchanged.
The independent matrix/outcome/archive/setup/identity-match flags are true for
the two complete current groups. Deployment/implementation/run/wall attestation,
hard aggregate storage, physical measurement and qualification remain false.

The next work binds the exact trusted setup and process/run to the supervisor,
then supplies actual aggregate storage enforcement and public I/O qualification.
Persistent Arduino applications, prompt synthesis/learning, real device/driver
and intelligence-hub providers, microscope commissioning and the rest of the
end-to-end objective remain unfinished. The full goal is active.

''' + anchor)
path.write_text(text)

path = ROOT / 'docs/prompt-to-pat.md'; text = path.read_text()
start = text.index('The [group-history stage]'); end = text.index('An operator says, for example,', start)
text = text[:start] + '''The [historical group reader](../artifacts/implementation/pat-io-group-history/results/README.md)
first independently checked a retained complete GPIO group. Its fresh deadline
failures and the later [page-encoding failures](../artifacts/implementation/pat-io-page-encoding/results/README.md)
remain preserved, including unresolved state.

The current [snapshot-reuse stage](../artifacts/implementation/pat-io-snapshot-reuse/results/README.md)
passes 132 distinct checks and completes fresh GPIO and PWM capture **and
independent inspection**. Each representative single-step constant candidate
has 30 cases, including all 25 fixed challenges. Separate pre-run setup, expected
outcomes, exact archive closure and operation/tick/record/byte accounting match.
The reader runs without file/SQL/clock access; forged archive variants refuse.
Pure snapshot reuse retains scalar distinctions, detached results and all
graph/generation/source/authority checks. Original execution limits remain.

This supplies complete current synthetic group evidence for those candidates.
Trusted process/run association, hard aggregate storage enforcement and public
qualification remain required before automatic PAT promotion. The result does
not establish deployment attestation, physical behavior, persistent controllers
or learned handling of arbitrary applications.

''' + text[end:]; path.write_text(text)

path = ROOT / 'docs/io-driver-hub-control.md'; text = path.read_text()
start = text.index('The [group-history stage]')
text = text[:start] + '''The current [snapshot-reuse stage](../artifacts/implementation/pat-io-snapshot-reuse/results/README.md)
passes 132 distinct methods, including complete fresh GPIO/PWM capture and
independent inspection. Each representative constant single-step candidate runs
30 cases, including all 25 fixed challenges and the shared pin/PWM/alias case.
Pre-run setup, exact responses and archive accounting match. Each group retains
26 states/52 databases; endpoint audits find no claims or owners. Earlier
[historical-reader](../artifacts/implementation/pat-io-group-history/results/README.md)
and [page-encoding](../artifacts/implementation/pat-io-page-encoding/results/README.md)
failures and their unresolved states remain preserved.

The bounded immutable snapshot cache preserves exact types, detachment and
validator identity while graph/generation/source checks and live authority reads
still run. No deadline, challenge or storage/effect ceiling changes. This proves
complete synthetic histories for the two tested candidates. Trusted process/run
association, actual aggregate quotas, public I/O qualification and real
device/driver/intelligence-hub lifecycle providers remain required.
'''; path.write_text(text)

path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
path.write_text('''# Remaining route from checked groups to I/O PAT qualification

This audit preserves the [finite I/O design](../../verification/io-pat-qualification-design/DESIGN.md)
and [timing/outcome design](../pat-io-timing-oracle-design/DESIGN.md). The current
[snapshot-reuse result](../pat-io-snapshot-reuse/results/README.md) passes 132
distinct methods and completes fresh GPIO/PWM capture with independent inspection.
Each tested candidate is constant and single-step, with 30 cases including all
25 fixed challenges. Complete group evidence is necessary; it does not authorize
automatic promotion or establish physical/deployment qualification.

| Required qualification evidence | Current authoritative evidence | Remaining work |
|---|---|---|
| Whole declared-domain compatibility and timing | Producer contracts and independent reconstruction agree for the two complete current groups; existing pure domain checks remain | Bind both computations to trusted service configuration/process/run identity; preserve unsupported-domain refusal |
| Exact nominal/boundary/negative matrix | All generated cases for the two constant candidates execute and are independently reduced, including four negative cases per group | The ordinary parameterized example still exceeds the original 32-case ceiling and refuses. Do not claim arbitrary parameterized/application coverage or drop cases |
| Completion objective versus fault response | Nominal completion and all 25 fixed expected responses are checked; fault failures remain failed candidate contracts | Preserve this distinction through supervision, evidence import and catalog promotion; unknown effects cannot become success |
| Nominal scheduler timing | Current groups compose exact nominal scheduling and all eight fixed forward-time challenges | Add trusted run/wall association and measured aggregate enforcement; virtual scheduling is not physical timing |
| Cancellation and reopen | The current groups execute and independently inspect the required cases in the ten-case lifecycle family | Bind immutable requests, authority and retained state to the supervised current attempt |
| Lost pending/completion replies | Required lifecycle loss/recovery and retained-read variants execute and are independently checked | Preserve inconclusive attempts, exact keys, effects and claims through supervisor death/recovery and service import |
| Exact replay and same-key conflict | Current nominal histories prove replay without extra effects and reject the changed request under original keys | Keep that association in public qualification; unsupported withdrawal/pruned-namespace contexts cannot inherit it or retry with replacement keys |
| Start/run/wall/lease/clock boundaries | All eight timing and three clock/guard checks dispatch per current group | Attest process/run association and service bounds; checked virtual histories do not establish physical clocks or real-time guarantees |
| Shared pin/PWM/alias exclusion and independent-pad progress | Both complete groups independently inspect the four-actor shared-resource challenge with exact setup, identities and effects | Bind provider identity and declared actors to the trusted service; enforce aggregate resources without masking guards or introducing hidden actors |
| Permission, binding and session changes | All three authority challenges and permission-related lifecycle variants execute and pass exact independent outcome checks in each group | Establish current service/configuration/run attestation. Changed dependencies require rechecking; old requests cannot silently rebind |
| Unresolved or contradictory evidence | Readers refuse missing/contradictory evidence; prior failed captures retain unresolved accepted work and claims | Supervisor must retain exact incomplete evidence and durable ownership without resetting state or relabeling refusal as zero unresolved effects |
| Current implementation/configuration identity | Selected imports and inputs are pinned; separate pre-run setup and recorded compiler/driver/worker identities match the current inspected groups | Complete trusted configuration, import-closure, artifact/policy/source/attempt/process/run association. Identity matching and the seven-package compiler profile are not deployment attestation |
| Group budgets and retained evidence | Both groups pass original capture guards and exact independent operation/tick/record/byte accounting; the actual lowered record-cutoff test passes | Supply hard aggregate storage enforcement and protected control capacity. Cooperative checks and closed filesystem accounting are not an enforced aggregate quota |
| Persistent service and public PAT tools | Fan-specific libraries and a separately staged supervisor exist; complete I/O group capture/inspection is now available | Finish fixed trusted service configuration, aggregate enforcement, durable ownership, serialized evidence import and atomic catalog association before mounting public I/O qualification |

The next implementation joins trusted pre-run setup, exact child process/run and
retained output association to supervision, then enforces actual aggregate storage
before public qualification or promotion. The current reader's matrix, outcome,
archive, trusted-setup and identity-match flags are true. Configuration,
implementation, run and wall attestation; hard aggregate storage; physical
measurement; and qualification flags remain false.

All earlier failures remain immutable: the [historical-reader stage](../pat-io-group-history/results/README.md)
includes wrapper/launcher/deadline failures, and the [page-encoding stage](../pat-io-page-encoding/results/README.md)
retains the 23-case deadline failure and an instrumented 11-case run with accepted
work, a running parent and one claim. The current stage retains its original
test expectation failure and the test-only correction. None of those states was
reconciled or replaced to obtain the passing fresh runs. No timing, effect, case
or storage ceiling was widened.

Finite I/O qualification still does not implement persistent Arduino controllers,
natural-language synthesis/learning, real driver providers, microscope commissioning
or intelligence-hub lifecycle/compute management. These remain part of the original
end-to-end goal; the two complete synthetic groups do not substitute for them.
''')
print('Reconciled complete current group evidence and remaining attestation/enforcement/public-service work.')
