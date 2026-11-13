# Local simulation control

`python3 -m hms` provides the experimental `hctl` CLI over a Linux pathname Unix socket. The initial backend executes simulation only. It does not install a Harness plugin, operate physical equipment, or implement the example WoT HTTPS forms.

Create a private directory and explicitly initialize a new simulation state:

```sh
mkdir -m 700 /tmp/hms-local-example
python3 -m hms serve --state-dir /tmp/hms-local-example/state --socket /tmp/hms-local-example/control.sock --init-simulation
```

The foreground process prints one JSON readiness record after binding and starting the runtime. Send SIGINT or SIGTERM to shut it down. Restart the same state without `--init-simulation`; ordinary startup never silently creates or resets a journal. The socket parent must already exist, belong to the invoking Unix user and have exactly mode `0700`. The socket is created with mode `0600`. Symlinked parent paths and every existing socket pathname are refused. An unclean exit can leave a stale socket: verify that its server is stopped before removing that file manually. Startup does not guess whether an existing endpoint is safe to replace.

State storage additionally requires a protected ancestor chain: each ancestor belongs to root or the invoking UID, with no group/other write access except a trusted sticky directory such as `/tmp`. The leaf is mode `0700`; existing DB, owner-lock and SQLite sidecar files are single-link regular files of the invoking UID with mode `0600`. An ordinary group-writable workspace ancestor is refused. Use a private deployment directory such as the example above. Same-UID/root changes and live state-directory renames remain outside this protection boundary.

Run client commands in a second terminal. `--socket` may appear before or after the subcommand:

```sh
python3 -m hms --socket /tmp/hms-local-example/control.sock discover --limit 20
python3 -m hms --socket /tmp/hms-local-example/control.sock describe INSTANCE
python3 -m hms --socket /tmp/hms-local-example/control.sock observe INSTANCE PROPERTY --max-age-ms 1000 --evidence-kind simulation
python3 -m hms --socket /tmp/hms-local-example/control.sock namespace --expires-unix-ms EXPIRY
python3 -m hms --socket /tmp/hms-local-example/control.sock prepare --params-file prepare-input.json
python3 -m hms --socket /tmp/hms-local-example/control.sock invoke --request-file invocation.json
python3 -m hms --socket /tmp/hms-local-example/control.sock operation OPERATION_ID
python3 -m hms --socket /tmp/hms-local-example/control.sock events OPERATION_ID --after 0 --limit 100
python3 -m hms --socket /tmp/hms-local-example/control.sock cancel OPERATION_ID
```

Replace `INSTANCE`, `PROPERTY`, `EXPIRY` and `OPERATION_ID` with values obtained from the runtime and an explicit future expiry in Unix milliseconds. `discover` also accepts `--capability` and `--cursor`; `describe --digest` supplies a known description digest. Invocation files contain the complete [host envelope](../spec/08-host-contract.md), including the server-issued replay namespace, explicit operation key and pinned immutable intent. The CLI parses the file before sending it; it does not invent current generations, authorization or a physically verified outcome.

`prepare --params-file` accepts an object containing `instanceId`, `actionId`, `arguments`, `operationKey`, `replayNamespace`, `timing` and `requiredEffect`. The runtime resolves current description and binding generations and returns `{request, requestDigest, admitted: false}`. Persist the returned `request` unchanged for submission and retries. Preparation does not reserve a resource or freeze preconditions; invocation performs admission again. The invoke reply is a current operation snapshot after durable submission. A background worker can already have advanced it to dispatching, running or completed; callers must inspect the returned state rather than assume it remains accepted.

Preparation, new invocation and dispatch also check the selected installed adapter. A published type, active binding and presence report are insufficient when the runtime has no matching handler, type, resource map or argument encoding. Such an installation returns `ADAPTER_INSTALLATION_UNSUPPORTED` before a new operation or resource claim is created. Support loss after acceptance is rechecked before dispatch. Existing keys still resolve their recorded operations, and historical receipts can still settle them; this check never converts an uncertain previous effect into a claim that nothing happened. Additional unsupported registry instances do not prevent supported local instances from refreshing or the runtime from reopening. Both drivers remain explicitly synthetic. The [installed-route profile](multi-adapter-runtime.md) now supports multiple local and compact routes under one authority, with an explicit operator catalog and named inherited streams.

For example, after saving a `namespace` command's result to `namespace.json`, create a bounded simulation request:

```sh
python3 - <<'PY'
import json, time
from pathlib import Path
now = time.time_ns() // 1_000_000
params = {
    "instanceId": "sim:home-fan", "actionId": "set_level",
    "arguments": {"level": 37, "unit": "percent"},
    "operationKey": "fan-example-1",
    "replayNamespace": json.loads(Path("namespace.json").read_text())["token"],
    "requiredEffect": "capability_completion",
    "timing": {"notBeforeUnixMs": now, "latestStartUnixMs": now + 60000,
               "maxRunMs": 5000, "latestCompletionUnixMs": now + 120000}
}
Path("prepare-input.json").write_text(json.dumps(params) + "\n")
PY
python3 -m hms --socket /tmp/hms-local-example/control.sock prepare --params-file prepare-input.json > prepared.json
python3 - <<'PY'
import json
from pathlib import Path
prepared = json.loads(Path("prepared.json").read_text())
Path("invocation.json").write_text(json.dumps(prepared["request"]) + "\n")
PY
python3 -m hms --socket /tmp/hms-local-example/control.sock invoke --request-file invocation.json
```

Use a namespace whose expiry covers this example's interval. The operation key identifies this one intent: changing its arguments while retaining the same namespace/key is a conflict, not a new experiment. This example changes only the synthetic plant.

Successful client commands print a JSON result on stdout and exit zero. Domain and local failures print `{"error":{"code":"..."}}` on stderr and exit nonzero. A transport timeout, broken connection or oversized response can occur after admission. Recover using the same invocation key and identical immutable intent or the returned operation id; do not create a new key merely because a reply was lost. The client makes one attempt and never retries automatically. Cancel requests use the runtime's operation semantics; disconnecting the CLI is not a cancellation request.

The CLI uses the checked Python client, which validates method-specific result schemas and correlates them with the retained request. `INVALID_RESPONSE` is an unusable reply, not proof of no admission or no effect. See the [API contract](../spec/10-local-api-contracts.md) for the exact result fields, cross-field checks and recovery boundary.

## Wire protocol and limits

Each connection carries one UTF-8 JSON object followed by one newline. The request has exactly `protocol: "hctl.local/0.1"`, `requestId`, `method` and `params`; `params` is an object and both ids use the host identifier grammar. The response echoes protocol/request id and contains either `result` or `error: {code}`. A request that cannot be assigned a validated id receives a null response id when a reply remains possible. Duplicate JSON keys and unknown envelope fields fail. Raw caller principal, deployment and Session fields are not accepted in the envelope.

| Method | Parameters |
|---|---|
| `discover` | Optional `capability`, `limit`, `cursor` |
| `describe` | `instanceId`; optional `digest` |
| `observe` | `instanceId`, `property`, `maxAgeMs`, `evidenceKind` |
| `namespace` | `expiresUnixMs` |
| `prepare` | `instanceId`, `actionId`, `arguments`, `operationKey`, `replayNamespace`, `timing`, `requiredEffect` |
| `invoke` | `request`: complete host invocation object |
| `operation` | `operationId` |
| `events` | `operationId`, `after`, `limit` |
| `cancel` | `operationId` |
| `procedure_submit` | `request`: complete immutable bounded procedure envelope |
| `procedure_status`, `procedure_cancel`, `procedure_resume` | `procedureId` |
| `procedure_events` | `procedureId`; optional `after`, `limit` |

The CLI spells procedure subcommands with hyphens, such as `procedure-submit
--request-file plan.json` and `procedure-status PROCEDURE_ID`. See
[bounded procedures](bounded-procedures.md) for key reservation, dependency
barriers, cancellation delivery and explicit restart continuation. Procedure
status remains compact; individual child operation queries expose detailed results.

Requests and complete responses, including their wrappers, are limited to 65,536 bytes excluding the newline. Therefore the local transport cannot carry an inner invocation already occupying the entire host-parser byte limit. Multiline JSON framing and pipelining are unsupported. The server admits at most sixteen active connection handlers and sets a listener backlog of sixteen. It acquires a worker slot before accepting a connection, so queued clients do not create unbounded application work.

Socket I/O uses a two-second monotonic deadline per accepted server connection; clients apply their own two-second connect/send/receive deadline. Slow incoming fragments do not reset that budget. Runtime methods execute bounded local transactions; socket deadlines cannot interrupt a blocking in-process handler or a stalled filesystem. Shutdown closes connection I/O and drains handlers before closing the runtime. It does not claim a two-second process termination guarantee.

## Local authority

The server derives `posix:<uid>` from Linux `SO_PEERCRED` and takes the deployment from the opened runtime. The client verifies that the connected server UID matches the private socket owner. Directory operations use a held directory descriptor via Linux `/proc/self/fd`, so binding and cleanup refer to the inspected directory. Cleanup removes only the inode created by that server. This transport requires a usable procfs and supports no TCP or abstract-socket fallback.

All processes with the same Unix UID share the same principal. This includes model-accessible shells and other local programs. A Session id, tool call id or socket pathname does not create per-agent authorization. Peer credentials describe the established connection; they do not identify a later recipient of a transferred connection descriptor. Session-specific delegation and isolation require a separate mechanism. The runtime still authorizes device/action/result access for the authenticated Unix principal.

The implementation follows the selected [Python socket documentation](https://docs.python.org/3.12/library/socket.html) and [Linux Unix-socket documentation](https://man7.org/linux/man-pages/man7/unix.7.html). [Archived evidence and precise reading coverage](../research/host-ipc/README.md) distinguish those source facts from the local protocol's design choices. Tests use real Unix sockets with a stub runtime; the combined runtime/CLI scenario is a separate integration check.
