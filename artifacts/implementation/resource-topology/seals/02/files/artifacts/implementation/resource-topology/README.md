# Staged pure resource topology contracts

This is the pure-contract step of the accepted [resource design](../../verification/io-driver-hub-resource-design/DESIGN.md), not an installed provider. All work stays in this staging directory. Live HMS sources, schemas, tests and runner were not modified. No Runtime, provider, hardware, model or acquired program was executed.

`staged/hms/resource_topology.py` exposes:

- `parse_topology(value)`: detached normalized topology, strict scalar/shape/byte limits, complete references, separate containment/dependency/alias DAG checks, typed GPIO/PWM/timer/bus footprints, exact canonical atoms and bounded consumer claim closures.
- `topology_digest(value)`: deterministic identity after order normalization of semantically unordered lists.
- `parse_generations(topology, value)`: one exact topology-bound generation snapshot.
- `binding_proof(topology, generations, instance_id)`: declared action roots, expanded atom IDs, relevant dependency generations, closure identity and a derived binding-generation identifier.
- `generation_change_claims(topology, target)`: reverse-dependent consumer claims plus the service/driver lifecycle atom, with a `refuse_if_busy` policy label. It changes no state and does not check whether resources are currently busy.

Three closed JSON Schemas cover topology, generation snapshots and binding proofs. The original `build_schemas.py` generates them. JSON Schema alone does not establish exact Python integer types, graph references, acyclicity, footprint completeness or installed support; the parser is required. For example, integral float tokens are rejected before canonicalization can turn them into integer tokens. Unexpected fields, missing/duplicate atoms, ambiguous atom/alias names, missing references, alias omissions, graph-depth and claim-limit overflow all refuse rather than truncate.

The only copied executable dependency modules are original HMS contract/Journal types and its existing canonical JSON implementation. The tests never construct Journal or Runtime. Ten baseline source/design inputs are pinned; acquisition of context files is not a new full-reading claim. Validation uses the existing installed `jsonschema` dependency stack. `validation-environment.json` records its files/versions after attempt 01 and before attempt 02; the matching after record is separate. This does not retroactively establish external-package stability during attempt 01 or claim a complete operating-system closure.

## Approved clarifications

The parent accepted these implementation decisions before testing; the sealed original design remains unchanged:

1. The generation document includes `profile`, which its prose field list omitted.
2. Every physical claimable node and every service/driver requires exactly one appropriate canonical atom. The parser refuses missing atoms even when a node is not currently consumed.
3. Historical generation-token nonreuse requires a future durable catalog. Accepting a single snapshot cannot prove it. Generation tokens may have equal spelling on different nodes.
4. Executable closure identity includes relevant typed properties, requires edges, aliases, atoms, consumer records and relevant generation values. It excludes global topology digest/revision and structural containment child lists. The complete topology digest remains in the proof as provenance. Unrelated changes can alter this provenance while preserving closure/binding identity; a future catalog must retain historical proofs rather than overwriting one binding generation with a different provenance blob.

The chosen synthetic service/driver/bus profile names are closed constants. GPIO access represents the first output-pulse capability and requires `push_pull_output`; PWM requires a declared channel/timer/pin route and `pwm_output`. Bus support here is footprint validation only. It neither models I2C electrical signaling nor executes transactions.

Pulse duration/duty/frequency arguments, installed action allowlists, electrical behavior, runtime authorization/support, actual claim/fence exclusion, lifecycle admission/publication/recovery and PAT eligibility integration remain later steps. This parser validates the topology's limits; it does not validate or run invocation envelopes. Caller-supplied physical relationships and driver digests are declarations, not attestations. Its sorted sets do not prove actual GPIO/PWM contention safety.

Independent review identified a required integration decision: `binding_proof` combines all actions of one instance, while `generation_change_claims` reports directly dependent consumers. Updating that shared binding generation can affect a sibling action whose own dependency set excludes the changed service. Before publishing actual generations, the catalog/provider must either use independently updated consumer instances, expand lifecycle exclusion to every action of each rebound instance, or implement finer binding publication. The current pure helper must not be plugged into multi-action rebinding as though it already resolves this transaction/lifecycle issue. It does not justify changing claims or clearing unknown work.

## Evidence and use

`attempts/01/` preserves the initial 18-test pass. Independent review then found that caller objects were deep-copied and recursively traversed before the JSON bounds check, allowing an unsupported `__deepcopy__` hook to run. The staged fix bounds and validates original objects first, rejects floats without normalization, and parses detached canonical bytes without caller-object copying. `attempts/02/` preserves the corrected 19-test pass with 14 exact local inputs unchanged; its added test rejects a custom-copy trap and oversized tree before unbounded copying/walking. Attempt 01 is retained unchanged and is not proof of the corrected source.

The tests establish GPIO/PWM pad intersection and independent-pad separation as contract properties; lifecycle scope excludes unrelated consumers; unrelated service generations leave closure identity unchanged while relevant generations alter it. They also cover bus/raw-pin overlap, all cycle types, malformed references, omitted atoms/footprints, strict numeric electrical bounds, duplicate addresses, detached output/order normalization, depth/count/claim limits, exact generation closure and no file/clock/database access during pure calls after schema import.

The test suite uses no external artifact/code oracle. `run_tests.py` imports only the staged HMS closure, forbids a live Runtime import in its receipt, and preserves each run in a new directory. A new run changes lane inventory and needs a new separate seal, not an overwritten historical receipt. `verify.py` checks the frozen index/attempt copies without importing HMS or running tests. Endpoint source stability is not an atomic filesystem snapshot or an edit-and-restore detector.

Await root review before integration. Existing live installations still support their declared simulation profiles; these staged documents do not add I/O or hub management to the public API.
