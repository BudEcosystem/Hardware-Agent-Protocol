# Installed simulation routes under one authority

The runtime can mount up to sixteen explicit installations, each using one of
two original drivers: a SQLite synthetic plant or a native compact C simulator.
Each installation exposes the existing fan, focus and inspection primitives
under its own instance identifiers. This demonstrates coexistence and durable
routing; it does not install arbitrary device code or qualify physical drivers.

The [installation schema](../schemas/adapter-installations.schema.json) and
[mixed example](../examples/installations/mixed-simulation.json) describe the
trusted operator file. Adapter identifiers, instance identifiers and compact
incarnations must be unique. Resource identifiers may deliberately coincide:
claims and fencing remain global across routes. Configuration accepts no command,
module path, port, URL or credential. The canonical descriptor is persisted with
a digest. Reopening with a supplied descriptor requires an exact match; omitting
the file uses the stored catalog. Dynamic add/remove/reconfiguration is not yet
an API.

```sh
mkdir -m 700 /tmp/hms-multi-example
python3 -m hms serve --socket /tmp/hms-multi-example/control.sock \
  --state-dir /tmp/hms-multi-example/state --init-multi-simulation \
  --installations-file examples/installations/mixed-simulation.json
```

That command opens the local route and records the compact routes as offline.
A trusted launcher can supply repeatable `--endpoint-route ADAPTER=FD` options.
Every FD must be an inherited, connected, same-user Unix stream. Duplicate open
streams, unknown route names and identity/manifest mismatches are refused. The
launcher uses `hms.installations.manifest_for` to obtain the exact manifest bytes
and digest and supplies the native fixture's existing identity options. HMS does
not launch endpoints or choose physical ports. Legacy `--init-simulation`,
`--init-compact-simulation` and `--endpoint-fd` remain supported.

Each backend owns its plant or compact protocol state, queue, counters and
worker. Acquisition clock labels are interpreted with the observation source
and endpoint session. Two compact routes can use the same boot number and label
while having different clock origins; matching labels alone never authorize
cross-device timestamp comparison or imply a simultaneous sample. Compact state, command mappings and packet history carry the adapter
identifier. Dispatch and result recovery resolve an operation through immutable
binding history, never the newest binding. Rebinding cannot send an old operation
to another endpoint. Unsupported installations fail before admission/dispatch;
retained-request replay still returns the existing operation. Missing-route
accepted work is rejected before handoff. Handed-off unknown work retains its
uncertainty and claims. There is no fallback to another backend.

A missing or invalid ready plant is left intact and made unavailable while other
routes can open. Planned provisioning can resume after interruption, but an
existing invalid store is never formatted automatically. Generated plant paths,
owner locks and SQLite sidecars receive the same private-file checks as the
original store. Offline compact routes preserve cached receipts and replay.
Stream reconnect requires runtime reopen; automatic endpoint restart is absent.
Legacy compact tables migrate in one transaction while preserving original
state bytes, packet IDs/wires, command rowids, payloads, receipts and counters.

Workers have separate route locks but share the Journal authority mutex and
resource namespace. ARM authorization and the HELLO clock measurement/publication sequence hold
that mutex through their bounded transport exchanges. Idle compact polling skips
authority-clock persistence when there is no accepted work to examine. Thus a slow route can delay another; there is no real-time
isolation or independent stop guarantee. Readiness publication batches the
existing checked presence, stream and observation ingress into one transaction.
This reduces repeated durable commits aging one snapshot while waiting to publish
it. The HELLO measurement and its publication also stay contiguous with respect
to other authority transactions. Acquisition timestamps and conservative receipt delay remain part of the
freshness calculation. A failed snapshot rolls back all its members; this is
not permission to increase a freshness limit or infer new sensor evidence.

Validation includes independently identified native endpoints, all three
scenarios per route, global shared claims/fences, historical result routing,
subset-offline recovery, boot faults, corrupt-store isolation, interrupted
provisioning, inherited-stream rejection and a genuine pre-catalog compact
migration. The real CLI test uses one local and two native routes with ordinary
host clocks, then reopens without compact streams and checks retained results.
It records bounded retries of an unchanged request after freshness refusals,
checking that each refusal left no replay key, new operation, claim or compact
dispatch mapping. It never retries an uncertain transport failure or an already
admitted failed operation. [The trace](../artifacts/verification/multi-cli-trace.json)
retains all refusals and completed scenarios; this is a functional test, not an
availability benchmark. Its three-second threshold is checked after a refusal;
a final attempt can begin after the backoff beyond that threshold, and each IPC
call has its own timeout. It is not a three-second wall-time guarantee. The
original invocation deadlines remain unchanged and enforced by the runtime.
The [runtime receipt](../artifacts/verification/local-runtime.json) is authoritative
for the exact tested inputs; the [independent review](../artifacts/verification/multi-adapter-code-review/)
records separate probes and limitations. The preserved 289-test snapshot and
older Harness receipts cover earlier code only.

The retained [failed 314-test run](../artifacts/verification/runtime-314-failed/index.json)
had one mixed-CLI freshness failure during concurrent validation. A later
[315-test run](../artifacts/verification/runtime-315-freshness/index.json) again
refused stale evidence at invocation after preparation; its other 314 tests
passed. These records precede the explicit retry coverage. Independent
before/after probes also preserve stale-readiness refusals under host load.
Batching and contiguous clock measurement reduce avoidable contention; they do
not establish a scheduler or storage latency bound. The final isolated live
probe completes nine scenarios without admission retries. A busy host can still
refuse admission when evidence is stale; qualification must measure its actual
workload instead of treating a later passing run as proof of bounded availability.
