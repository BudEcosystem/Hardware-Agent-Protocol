# Isolated application-intent handoff

Status: source prepared on 2026-11-09; the root reviewer subsequently ran the
focused suite: 22 tests passed with zero failures/errors in
`test-attempt01/receipt.json`. Core and interpreter pins remained unchanged.
The source-preparation author did not import or execute the candidate. Demo
execution, if any, has separate receipts. Public HMS Runtime, schema,
CLI, MCP, Harness tools and qualification mounts are unchanged.

This prototype persists natural-language intent revisions and an agent's closed
PAT proposal. It implements no semantic parser, planner, experience learner,
qualifier, promotion or application execution. The caller may use an existing
agent to interpret the retained prompt after observing real discovery results.
Fresh arbitrary prose is not classified as a known scenario by this store.

## Components and authority

- `intent_handoff/contracts.py`: closed bounded request shapes, exact original
  numeric-type checks, retained HMS PAT parsing/static input checks, and existing
  HMS read-request/result validation. It accepts a supported-syntax candidate or
  explicit unresolved outcome; syntax support does not prove qualifier support.
- `store.py`: immutable constructor-anchored owner/store identity/capacity and one
  append-only mutation table. Requests retain exact canonical request and original
  result for replay. Every request verifies the complete bounded chronological
  history and reconstructs current revisions/proposals; no repair occurs.
- `consumer.py`: one checked wire dispatcher and explicit agent consumer seam.
  The host supplies its authenticated principal outside request JSON. A JSON
  `principal` field is invalid. This is an embedding contract, not a new
  authentication server or per-agent permission system.
- `integrity.py` plus `dependencies/`: exact retained HMS parser/read-validator
  closure and schemas. Pins and loaded module origins are checked. Installed
  Python/jsonschema remain runtime prerequisites; this is not hostile-host code
  attestation or proof of physical truth.

The three methods are `intent_put`, `intent_get`, and `proposal_put`. Requests use
the profiles in the prior design packet. The implementation fixes these bounds:
8192 UTF-8 prompt bytes, 4096 interpretation/detail bytes, eight discovery rows
with 16384 total canonical bytes, 32768 request bytes, and 65536 record bytes.
Capacity is immutable and explicitly supplied both at creation and reopening:
`maxRecords` is 1..129 and `maxBytes` is 512..8388608. Metadata is one charged
record; every intent/proposal mutation is another. Its complete retained request,
result and a 40-byte logical framing charge count toward capacity. There are no
additional uncharged dedup/history tables. These are logical limits, not physical
SQLite/sidefile quotas, reserved recovery capacity or bounded latency claims.

An exact mutation-key replay returns the original result even after a later
proposal/revision, including when capacity is full. Changing the request or method
under that key conflicts. New revisions compare the expected current revision;
one proposal may be committed per revision. An uncommitted stale proposal refuses.
A deliberately revised planning attempt needs a new explicit intent revision.
No prompt normalization is performed: UTF-8 text, combining characters, spaces
and line endings are retained. Canonical JSON encoding may differ from the
original transport's JSON escaping; decoded prompt bytes remain exact.

The owner-controlled SQLite file must reside in a trusted private directory.
Creation uses an exclusive new file, reopening requires the same constructor
anchors, transactions use synchronous FULL, and close serializes with requests.
Creation failure leaves its artifact for inspection. Filesystem/directory-fsync,
hostile path replacement, and an owner restoring an entirely coherent older
database are outside this small profile. Checks detect malformed/inconsistent
history; they are not an external anti-rollback authority. There is no pruning,
eviction, automatic reset, automatic planner retry, or identity reuse.

## Agent use and discovery

An existing agent can read a handoff, explicitly inspect installed capabilities,
then submit a proposal. `AgentConsumer.inspect` permits only discover, describe,
and observe, validates parameters before calling the injected existing read
bridge, and validates the returned carrier and method-specific success result.
Refusals retain their code and unconfirmed carrier. The explicit bridge performs
the provider's declared read behavior: an observation may require acquisition.
Calling something a read does not establish effect-free physical observation.
Store startup, reads, writes and exact replay never call that bridge, a planner,
prepare/invoke, or a qualifier.

Discovery attached to a proposal is attributed planning context, not trusted
current evidence. Session/call/model identifiers are attribution only;
`attributionVerification` is always `unverified`. Every retained proposal reports
qualification `unavailable` with `PUBLIC_QUALIFICATION_MOUNT_UNAVAILABLE`.
The candidate's finite simulation outcome contract remains unchanged.

For later integration, a qualified structured-trigger service must run before
AgentLoop to support zero planning calls. It must retain current eligibility,
original effect uncertainty, and replay identities. This prototype neither
classifies evidence loss as novelty nor bypasses the documented public
qualification storage/control-capacity prerequisites. Driver, I/O, hub, standing
controller and physical-provider requirements remain part of the larger goal.

## Prepared verification

After source review, the intended isolated command is:

```sh
python3 -B -I artifacts/implementation/prompt-intent-handoff/run_tests.py --output /absolute/path/to/new-attempt
```

The parent directory must already exist; the attempt directory must not. The
runner retains before/after core/test/runner/dependency pins, interpreter hash,
log, monotonic elapsed time and a receipt. It applies per-process limits of
30 CPU seconds, 512 MiB address space, 1 MiB per file, 64 descriptors and no core
dump (or stricter inherited hard limits). This is not hostile sandboxing or
aggregate child-tree containment. One owned bounded subprocess checks reopening
the persisted proposal in an independent interpreter, with a 30-second timeout,
reaping, and retained exit/stdout/stderr hashes.

Tests cover replay/revisions and exact prompt bytes; unsupported outcomes; closed
shapes and original numeric types; static PAT refusal; owner/identity/capacity
anchors; full-store behavior; mutable caller aliases; concurrent writers and
close ordering; pre-commit rollback and lost post-commit outcome; independent
process reopening; corrupt records/schema/metadata; actual existing read schema
validation; and absence of automatic authority/hardware/planner execution.
`tests/fan-artifact.json` is a retained existing fixture. Its use is labeled
`scripted-fixture` and is not evidence of semantic planning or learning.

The separate [two-stage demonstration](demo/INTENT_STEPS.md) first retains a real isolated legacy
simulation discovery/description/observation transcript and an arbitrary prose
intent. A current external agent then authors its proposal from those outputs;
a separate submit command commits that supplied file. Collection contains no
hardcoded proposal. This cannot be called a Harness AgentLoop model run, physical
learning, qualification, or deterministic application reuse.
