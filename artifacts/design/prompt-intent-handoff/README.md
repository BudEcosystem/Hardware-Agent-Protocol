# Prompt, agent handoff, and learned PAT gap audit

Status: source-only audit, 2026-11-09. This packet does not implement or run a
planner, qualification worker, application, model, MCU, or physical provider.
No candidate code was imported. Shell activity was limited to source reading,
copying, source hashing/counting, and creating this requested audit packet.
`SOURCE_SHA256SUMS` pins 30 exact source copies; `READ_SCOPE.json` distinguishes
full-file review, selected ranges, and interface-only inspection. A retained copy
does not imply that its entire content was reviewed or executed.

The next independent implementation should make an arbitrary user intent a
durable, revisioned agent handoff and retain the agent's closed PAT proposal.
This is a real missing user-path component. It must stop at a proposal until the
existing qualification service can be mounted under its stated storage and
control-capacity prerequisites. Neither prompt memoization nor a synthetic
success demonstrates learned physical application behavior.

## What exists and what is missing

| Path | Observed implementation | Remaining connection |
| --- | --- | --- |
| `hms/pat_contracts.py` | Closed finite sequence, typed bounded parameters, literal/parameter expressions, static predicates, simulation-only outcomes | No natural-language interpretation, dynamic observation predicate, loop, branch, standing controller, or physical-effect profile |
| `hms/pat_catalog.py` | Immutable candidate publication, evaluator receipts, conflicts, revision-checked promotion, current eligibility | No learner derives a new candidate from experience; the generic evaluator callback is not the durable original-run qualification boundary |
| `hms/pat_execution.py` | Typed trigger, complete bounded candidate/binding enumeration, one eligible selection, durable instance/procedure association, unchanged-key replay | No prose ingress, durable intent interpretation, novelty coordinator, agent handoff, or experience-to-candidate coordinator |
| `hms_qualification/vault_recorded_io/` | Original supervised run and imported evidence association, independent reduction, owner-held complete evidence view, current source applicability, promotion and deterministic admission | This is an explicit host library, not a public Runtime/Harness service; physical qualification is explicitly false |
| `hms/runtime.py:441` | Checked public dispatch for primitives and finite procedures | No intent/PAT/qualification methods or installed learning coordinator |
| Harness installed overlay | Nine native/PTC hardware tools share one checked local provider; real tool results can enter model-visible Session history | No intent or PAT tools; even the five existing HMS procedure methods are not yet projected in this retained overlay |

`PAT_NO_MATCH` is not a sufficient novelty classifier. A candidate may be absent,
not active, or ineligible under changed dependencies; evidence unavailability,
unknown prior effects, resource contention, and unsupported capability profiles
must not be converted into permission to invent another actuation attempt.
The planning-only increment should report its lack of an installed qualified
selector explicitly, rather than claim that an exhaustive current catalog lookup
proved novelty.

The full objective remains: interpreted application intent -> context-sensitive
planning -> verified execution/outcome traces -> a proposed generalized PAT ->
independent domain qualification -> policy-authorized promotion -> fresh eligible
typed triggers without planning. The proposed first increment implements only the
first handoff and durable proposal, with explicit integration slots for the rest.

## A source-derived qualification-domain mismatch

This is arithmetic from the pinned sources, not an executed qualification result.

`hms/pat_io_combined_matrix.py` declares `maxCases=32`, 24 fixed `SCENARIOS`, and
one resource challenge. `IoSequencePolicy.generate_cases` in
`hms/pat_io_contracts.py` creates the candidate-domain cases before those 25
fixed cases are added.

| Candidate | Candidate-domain cases | Fixed cases | Combined requirement |
| --- | ---: | ---: | ---: |
| No parameters | 1 merged nominal/boundary + extra parameter + 3 wrong-context cases = 5 | 25 | 30 |
| One ordinary singleton integer parameter | 1 merged nominal/boundary + boolean + integral-number + below-domain + above-domain + missing parameter + extra parameter + 3 wrong-context cases = 10 | 25 | 35 |
| One ordinary non-singleton integer range with a distinct midpoint | 3 nominal/boundary + the same 9 negative cases = 12 | 25 | 37 |

The source rejects a combined total above the ceiling with
`PAT_IO_MATRIX_COMBINED_LIMIT`; it does not truncate cases. Integer parameter
support in the generic compiler and static I/O policy therefore does not establish
that the complete installed original-run qualifier accepts that parameterized
domain. A claimed learned parameter-generalization demonstration needs this
profile/budget mismatch resolved and its entire revised qualification path
revalidated. Do not silently raise a constant, omit fault cases, or relabel a
parameterless artifact as a general policy. The table's parameter examples assume
ordinary finite primitive domains with both below/above representable values;
it is not a claim of executing every possible artifact.

## Small next implementation contract

`CONTRACT.json` is a proposed field contract, not a mounted API or an executable
JSON Schema. Use a new isolated candidate with one bounded intent/proposal store,
one thin handler, and one Harness consumer. Do not build a general task queue,
agent scheduler, new model client, or autonomous actuation service.

1. **Put an intent revision.** Preserve the exact prose, application identity,
   expected previous revision, and caller operation key. Return the stored
   revision/digest and a durable `awaiting_proposal` handoff. Changed prose or
   requirements create a new revision; they never rewrite a historical revision.
2. **Read the handoff.** The already-running agent reads it and calls existing
   `hardware_discover`, `hardware_describe`, and `hardware_observe` as needed.
   Preserve the actual tool replies and source identifiers as bounded planning
   context. Their presence is not independent qualification or present authority.
3. **Commit the agent proposal.** Accept exactly one closed supported-candidate
   or unsupported/ambiguous outcome for the current intent revision and handoff
   digest. A supported proposal contains an interpreted objective, typed initial
   parameters, and an artifact validated by the existing `parse_pat` and
   `validate_parameters`; correlate task/input identifiers to the artifact.
   The store computes identities. The agent cannot supply a pass flag, evaluator
   receipt, promotion state, driver code, arbitrary source path, or authority.
4. **Return honest progress.** `proposed` means syntax and identity checks passed.
   Qualification remains `unavailable` in this increment, with the documented
   prerequisite. No method executes, promotes, or claims that learning occurred.

The handoff identity should be deterministically derived from the store identity,
application identity, revision, and exact intent digest. The intent revision is
the single planning slot; re-reading it never starts a model. The trusted ingress
owns the choice to invoke an existing agent once. A repeated delivery returns the
same handoff/proposal; a different proposal under the original operation key
conflicts. A proposal for a superseded revision refuses and cannot affect the new
revision. A deliberate second planning attempt requires an explicit new revision
in this first small profile, rather than an implicit retry/job system.

Retention must bound total records and canonical bytes before mutation, including
idempotency keys and historical revisions/proposals. Refuse when full; never evict
an identity silently and reuse it. Persist mutation plus deduplication atomically.
Restart reads the retained handoff/proposal; it does not call a model, mint a new
revision, or reinterpret unknown effects. Logical row/byte bounds are not proof
of filesystem-wide aggregate quotas or protected control capacity. Keep the first
store isolated from the live authority until its mount is separately justified.

Planner Session/call/model identifiers are attribution only. The local service's
existing authenticated principal determines permission to create/read/propose.
The small profile should use one configured owner, not introduce speculative
per-agent delegation. Proposal authority is separate from administrator-owned
qualification configuration and promotion policy.

## Existing Harness supplies generation

The retained native package has the actual `ctx.tools.register` consumer and
`ctx.hardware.request` provider seam. The provider already forwards one checked
Python `Client.request` without automatic mutation retry. Extend a new owned
Harness clone/profile, not the retained historical checkout. If the intent surface
is later added to HMS's checked local API, update its schema/validators and runtime
dispatch together, then the HardwareMethod union, method descriptions, generated
output mapping, exact method-set test, and registration teardown. The generic
provider does not need another model or transport integration.

For the immediate isolated profile, an intent service/tool contribution can sit
beside those hardware tools and use the same native/PTC registry and Session
attribution. It must have a checked local planning-only boundary; a direct SQL
helper inside the model-visible tool must not be treated as the final public API.

The already-configured Harness AgentLoop may interpret a newly delivered prose
intent and return the proposal through this tool. No LLM credentials or model
availability are established by this audit. If the current external agent instead
generates the proposal after observing actual tool results, record it as an
external-agent planning run; do not relabel it as an AgentLoop model invocation.
The source's `ScriptedAdapter` proves dispatch/history wiring only. It is not
evidence of semantic interpretation or learning.

Later, a trusted structured-trigger consumer must consult the deterministic PAT
service **before** entering AgentLoop. Existing Harness commands or a service
consumer can call tools/services directly; calling `agent.followup` or a scripted
model on every trigger cannot demonstrate zero planner calls. Fresh arbitrary
prose may still need interpretation even if an eligible artifact ultimately
matches. A stored intent handle plus typed context makes the no-planner path
testable without pretending that raw language matching is solved.

## Join the qualified path only at its existing boundary

Once the stated public-mount prerequisites are satisfied, a trusted coordinator
can associate a proposal with the original configuration/run/import identities:

`IoServiceConfigurationStore.configure/prepare_run` ->
`IoServiceRunStore.reserve` -> `IoServiceExecutionStore.execute/recover` ->
the existing evidence reduction/vault import authority ->
`VaultRecordedPatCatalog.record_evaluation` ->
revision-checked `transition(... target='active')` ->
`VaultRecordedPatExecutionStore.run`.

The first three APIs were inspected for their interfaces, while `io_services.py`
and the entire recorded catalog/bridge/execution package were read. This packet
does not claim a fresh complete execution or complete implementation audit of the
supervisor/vault producer chain. Keep its original run, publication, manifest,
dependency and complete held-inventory checks; never replace them with a custom
callback that returns `passed`. The recorded catalog explicitly disables the
legacy evaluator entrypoint and always records `physicalObjectiveVerified=false`.

Public qualification remains gated on bounded storage before mutation/recovery,
hard aggregate accounting across writers/sidefiles, backed control capacity, and
control-only recovery when bulk storage is full/unavailable. The planning handoff
does not satisfy or waive these requirements.

## Meaningful verification of this increment and the later objective

For the next implementation, verify a non-prebaked prose prompt through actual
discovery/tool replies and an actual agent-generated proposal, retaining exact
prompt, tool exchanges, proposal, digests, and attribution. A hand-authored fixture
or scripted adapter is useful for repeatable wiring tests but must be labeled as
such. Include a revised intent, unsupported device behavior, stale proposal,
same-key conflict, process reopen, invalid artifact, and full-store refusal. Verify
no qualifier, promotion, procedure, or primitive invocation occurs in this profile.

For the eventual full path, separately verify:

- First unfamiliar **supported** intent: one real planning handoff, proposal,
  actual original-run qualification and outcome evidence, permitted promotion.
- A later eligible typed context under the same interpreted revision: a new
  application run uses the eligible PAT with zero planning invocations; exact
  delivery replay retains the original run/procedure/child identities.
- An altered supported context outside the qualified domain: a durable planning
  exception; evidence loss, unsupported hardware, ambiguity and unknown effects
  have distinct restore/refusal/reconciliation outcomes.
- Instrument all planner entry paths and model `prepareCall`/`stream`, plus any
  external planner and pinned inference service. Zero API network calls alone
  is insufficient. Report planning, perception and other inference separately.
- Retain failures and measured task outcomes as experience; derive a changed
  candidate/domain from those records and independently qualify it. Merely storing
  a successful literal program beside its prompt is not learned generalization.

The same objective eventually covers device I/O, installed drivers and hub
capabilities through advertised resources, dependencies and lifecycle contracts.
This first intent schema does not hardcode an Arduino/GB10 branch or assert that
those physical providers exist. Missing driver, bus, hub/compute, feedback or
standing-controller profiles remain explicit unsupported capabilities. A prose
requirement cannot manufacture those providers or their qualification.
