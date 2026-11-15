# Deploying a gateway

This guide shows how to put several device servers behind one BHMS gateway with principals, scopes and narrowed
bounds, how to check a policy before it serves (`bhms gateway check-policy`), and what to decide before a gateway runs
for real (listeners, TLS, state, restarts). The keys of the configuration file are listed in the
[gateway configuration reference](../reference/gateway-config.md); the rules are in [spec 7.4 to 7.6](../../../spec/bhms/07-leases-and-authority.md#74-authority)
and [spec 13](../../../spec/bhms/13-security.md). Every block below is executed by the docs test.

## What a gateway is for

- One endpoint for many device servers, each in its own namespace (`pump/pump-1`, `thermo/thermo-1`). It spawns stdio
  upstreams (and restarts them), connects to running ones, and bridges BHMS-Compact microcontrollers.
- **Authority**: principals by token (WebSocket, HTTP) or uid (Unix socket), scopes per principal, and bounds that narrow
  action arguments per principal. Device servers behind it can stay single-principal.
- **Its own journal**: every forwarded invoke is recorded before it is sent, with a deterministic upstream key, so a
  gateway restart never makes an action run twice.
- **Cross-device leases** and a **stop** that fans out to every upstream ahead of everything else.
- **Isolation**: a dead or slow upstream makes its devices `offline` and its calls time out (`upstream_timeout_ms`),
  without affecting the others.

## Check a policy before it serves

The repository's example gateway, [`examples/bhms/gateway.toml`](../../../examples/bhms/gateway.toml), serves three
simulated devices to an agent, an operator and a stop-only safety principal. `check-policy` starts the upstreams
without serving anything and lists, per principal and scope, what each scope matches among the devices actually served:

```sh run
bhms gateway check-policy examples/bhms/gateway.toml
```

```text output
3 devices served
principal agent
invoke:bench/*/*: bench/stage-z/move_to
stop:bench/*: bench/stage-z
invoke:pump/*/*: pump/pump-1/dispense
principal operator
admin: everything, including other principals' operations
principal safety
stop: ...
```

## Write the policy

A principal is a name, how it is recognised (`tokens` as sha256 digests, never plaintext; or `uids` for Unix-socket
peers), its `scopes`, and optional `bounds`. Compute the digests and the default agent scopes with the SDK:

```python run
from bhms import token_digest
from bhms.runtime.authority import agent_scopes

print(token_digest("lab-agent-token"))
print(list(agent_scopes("pump/*", "thermo/*")))
```

```text output
sha256:96c4fd0684a6387c7b24b383ad916190b9fa03a9312ab0bb59d00a7824b7b976
['read', 'lease', 'invoke:pump/*/*', 'stop:pump/*', 'invoke:thermo/*/*', 'stop:thermo/*']
```

The default agent policy includes `stop` on the agent's own devices on purpose: when something goes wrong, stopping is
the one safe action an agent has, and a principal that can start motion but not stop it is a policy mistake
(BHMS-AUTH-015). Hazardous actions are never granted by a glob: the scope must name the action, for example
`invoke:oven/oven-1/heat_to` (BHMS-AUTH-003).

| Scope | Grants |
|---|---|
| `read` | discover, list and describe devices, retained reads, events, subscriptions, the principal's own operations |
| `invoke:<deviceGlob>/<actionGlob>` | invoking matching actions (split at the **last** `/`: behind a gateway write `invoke:pump/*/*`) |
| `invoke:cap:<capabilityGlob>` | invoking any action of devices with a matching capability (never a hazardous one) |
| `lease` | `leases/acquire`, `renew`, `release` |
| `stop`, `stop:<deviceGlob>` | `stop` on all, or matching, devices |
| `programs:run`, `programs:register` | running and registering programs (on a device server: a gateway does not offer programs) |
| `operations:read` | seeing other principals' operations (never cancelling them) |
| `operations:resolve` | `operations/resolve`: asking a device again about an unknown operation, and recording an operator's resolution |
| `admin` | everything, including other principals' operations |

Save as `lab-gateway.toml` (the two upstreams are the repository's example pump and thermometer):

```toml file=lab-gateway.toml
[gateway]
id = "lab-gw"                                # part of every derived upstream key: keep it stable across restarts
state_dir = "lab-state"                      # the forwarding journal and fences (relative to this file)
listen = ["unix:lab-gateway.sock", "ws://127.0.0.1:8765", "http://127.0.0.1:8766/bhms"]
upstream_timeout_ms = 5000
instructions = "Lab bench: a syringe pump and a thermometer. Lease pump/pump-1/plunger before dispensing."

[[upstream]]
name = "pump"
stdio = "{python} {config_dir}/examples/bhms/pump_server.py"
env = { BHMS_STATE_DIR = "{config_dir}/lab-state/pump" }

[[upstream]]
name = "thermo"
stdio = "{python} {config_dir}/examples/bhms/thermo_server.py"
env = { BHMS_STATE_DIR = "{config_dir}/lab-state/thermo" }

[principals.agent]                           # token lab-agent-token
tokens = ["sha256:96c4fd0684a6387c7b24b383ad916190b9fa03a9312ab0bb59d00a7824b7b976"]
scopes = ["read", "lease", "invoke:pump/*/*", "stop:pump/*", "invoke:thermo/*/*", "stop:thermo/*"]
bounds = { "pump/pump-1/dispense" = { volume = { maximum = 50 } } }

[principals.operator]                        # token lab-operator-token
tokens = ["sha256:cd04edb41c8d68d38c4e60685c4c8992d58effaba56e9338a0cf0e4ffb7681e6"]
scopes = ["admin"]

[principals.safety]                          # token lab-safety-token: can stop devices and nothing else
tokens = ["sha256:84724cf7c152a7890f65256723a6990f8cf94534fec82729c040be3ca6b87d0a"]
scopes = ["stop"]
```

`bounds` can only narrow: a bound wider than the device's own is refused when the gateway starts. A principal sees its
narrowed schema in `devices/describe`, so an agent is told the limit instead of discovering it by refusal.

### Policy mistakes `check-policy` catches

A scope that matches nothing fails closed, and silently: every request is refused and nothing says why. `check-policy`
says so, and `--strict` turns any warning into exit status 1 for CI:

```sh run exit=1
sed 's#invoke:pump/\*/\*#invoke:pump/*#' lab-gateway.toml > typo-gateway.toml
bhms gateway check-policy typo-gateway.toml --strict
```

```text output
principal agent
invoke:pump/*: matches nothing
WARNING: matches nothing: the pattern splits at the last "/", so it names actions of a device 'pump', which does not exist; for the actions of the devices matching pump/* write invoke:pump/*/*
```

`--json` prints the same report for tools.

## Run it

```sh run background wait=tcp:127.0.0.1:8765
bhms gateway lab-gateway.toml
```

(`python -m bhms.gateway lab-gateway.toml -v` is the same with INFO logs.) The agent sees both devices with its narrowed
bound. `dispense` requires a lease; `bhms call`, like the agent tools, acquires one on exactly the action's resources and
releases it when the operation settles:

```sh run
export BHMS_TOKEN=lab-agent-token
bhms ls ws://127.0.0.1:8765
bhms describe ws://127.0.0.1:8765 pump/pump-1
bhms call ws://127.0.0.1:8765 pump/pump-1 dispense volume=20 --key dispense-1
```

```text output
pump/pump-1 Syringe pump online bhms.liquid.dispense dispense dispensed_total
thermo/thermo-1 Bench thermometer online bhms.sensor.temperature - temperature
action dispense(volume: number uL 1..50 step 0.1) effect=irreversible repeat=relative lease=required cancel=no evidence=reported max=10s -> {dispensed: number uL}
pump/pump-1.dispense op-... completed: dispensed 20 uL (effect unverified, ...)
```

The same principal over Streamable HTTP:

```sh run
BHMS_TOKEN=lab-agent-token bhms read http://127.0.0.1:8766/bhms pump/pump-1 dispensed_total
```

```text output
pump/pump-1.dispensed_total = 20 uL (simulated, valid, ... old)
```

The safety principal can stop, and nothing else:

```sh run exit=1
export BHMS_TOKEN=lab-safety-token
bhms stop ws://127.0.0.1:8765 pump/pump-1
bhms call ws://127.0.0.1:8765 pump/pump-1 dispense volume=5 --key safety-try
```

```text output
stop not confirmed on 1 of 1 devices (1 unsupported): pump/pump-1 unsupported (no physical stop) Next: stop them by other means (0 operations canceled)
Refused: no device 'pump/pump-1' (gateway policy rule scope:read). Next: devices/list shows the devices you can use [rule: scope:read].
```

The example pump declares no stop procedure, so its stop is `unsupported`: queued work is cancelled and leases are
revoked, and the summary says plainly that nothing physical was commanded. A principal without `read` is told the
device does not exist (BHMS-AUTH-002), not that it exists and is forbidden.

The Unix socket's owner (your uid; `trust_same_uid` is on by default) is `admin` and sees every principal's
operations. For admin principals each forwarded operation also names the upstream server's own operation id
(`upstream`), so the gateway's record can be joined to the device server's journal after an incident:

```sh run
bhms ops unix:lab-gateway.sock
bhms ops unix:lab-gateway.sock --json | grep -A2 '"upstream"'
```

```text output
OPERATION WHAT STATE EFFECT UPDATED
op-... pump/pump-1.dispense completed unverified ...
"upstream": {
"server": "pump",
"operationId": "op-..."
```

## Change the policy without a restart

`SIGHUP` re-reads `[principals]` and applies it to new requests at once; admitted operations continue under the authority
they were admitted with. A file that does not load leaves the old policy in place (the gateway logs why).

```sh run
cat >> lab-gateway.toml <<'EOF'

[principals.viewer]                          # token lab-viewer-token: read only
tokens = ["sha256:3ee609f994a25da0d680b10d742dcb94e23377d7206a6c78345c3f49367cbe6f"]
scopes = ["read"]
EOF
pkill -HUP -f "[b]hms gateway lab-gateway.toml"     # [b]: the pattern must not match this shell itself
sleep 1
BHMS_TOKEN=lab-viewer-token bhms read ws://127.0.0.1:8765 thermo/thermo-1 temperature
```

```text output
thermo/thermo-1.temperature = ... Cel (simulated, valid, ... old)
```

## Before it runs for real

- **Listeners and TLS.** A non-loopback listener must use TLS (BHMS-SEC-004), and the TOML file has no TLS options: run
  the gateway on `ws://127.0.0.1:<port>` or `http://127.0.0.1:<port>/bhms` behind a TLS-terminating reverse proxy on the
  same host, or embed it and pass `ssl=` to `Gateway.listen`. A `wss://` or `https://` URL without a TLS context is
  refused rather than served in clear. Unix sockets need no token: the peer's uid is the identity. Set
  `trust_same_uid = false` and list `uids` when other accounts on the host must not be admin.
- **Tokens.** Only digests go in the file; hand each token to its principal through a secret store or an environment
  variable (`BHMS_TOKEN` for the CLI and `bhms mcp`). Upstreams that need a token get it with `token_env` or `token_file`.
- **State.** `state_dir` holds the forwarding journal and fences. Keep it on a local disk that survives reboots, back
  it up with the device servers' own state directories, and never share it between two gateways: `id` and `state_dir`
  together are the gateway's identity for idempotency.
- **Durability.** The default `durability = "dispatch"` fsyncs before forwarding an invoke; the measured cost is in
  [performance](../performance.md).
- **Upstreams.** `upstream_timeout_ms` bounds every call; `health_interval_ms` and `health_timeout_ms` decide when an
  upstream's devices read `offline`; `queue_size` and `max_inflight` decide when the gateway answers `BUSY`.
- **Microcontrollers.** `type = "compact"` upstreams ([Arduino guide](arduino.md), [compact example](../../../examples/bhms/compact-gateway.toml)).
- **Agents.** Point `bhms mcp` (or the OpenAI adapter) at the gateway with the agent's token, never at the device
  servers directly ([connecting agents](connecting-agents.md)).
- **Conformance.** `bhms conformance gateway` runs the gateway profile against the built-in fixture
  ([running conformance](conformance.md)).

A systemd unit for a gateway (not run by the docs test: it installs a service):

```ini no-run
[Unit]
Description=BHMS gateway (lab bench)
After=network-online.target

[Service]
User=bhms
WorkingDirectory=/srv/bhms
ExecStart=/srv/bhms/.venv/bin/bhms gateway /srv/bhms/lab-gateway.toml
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
