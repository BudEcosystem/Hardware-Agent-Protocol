# BHMS benchmarks

One command, JSON results, an explicit pass/fail per budget. Read [docs/bhms/performance.md](../docs/bhms/performance.md) for
the numbers and what they mean.

```
pip install -e 'sdk/python[http,mcp]'            # bhms with the gateway's HTTP binding and the MCP bridge
(cd sdk/typescript && npm ci && npx tsc)          # optional: enables the TypeScript comparison
python bench/run.py --quick                       # smoke sizes, about two minutes
nice -n 10 taskset -c 17,19,21,22,23,24,25,31 \
  python bench/run.py --full --label amd --cpus 17,19,21,22,23,24,25,31 --node ~/node/bin/node
```

`--only invoke,fsync` and `--skip ts_vs_py` select scenarios; `--state-root DIR` (or `$BENCH_DIR`) is where durable state is
written, which decides the fsync cost: put it on the filesystem you want to characterise (not tmpfs). Results land in
`bench/results/<date>-<host>[-label]/`: `environment.json`, `<scenario>.json`, `budgets.json`, `summary.json`.

## Scenarios (`bench/scenarios/`)

| scenario | measures | reuses |
|---|---|---|
| `fsync` | `fdatasync`/`fsync` latency of the state directory's filesystem (the durability floor), raw SQLite WAL commit | `invoke_roundtrip.commit_latency` |
| `transports` | ping round trip and pipelined throughput over unix, tcp, websocket, stdio (no device runtime) | `bhms.cli.bench.measure` |
| `invoke` | `actions/invoke` per transport (unix, ws, stdio) x durability (full, dispatch, process, memory) x `waitMs` 0/1000 | `bhms.cli.bench.measure` |
| `concurrency` | 1/10/100 clients, same device vs spread over 100 devices, dispatch vs process | |
| `gateway` | 1,000 upstreams / 10,000 devices: start-up, `devices/list` paging, event fan-in, per-invoke gateway overhead | `sdk/python/benchmarks/gateway_scale.py` (imported) |
| `gateway_http` | the same catalog and an invoke over Streamable HTTP versus the gateway's unix socket | |
| `subscription` | one event stream to 1/10/50/100 listeners, per-delivery latency | |
| `recovery` | SIGKILL with N running operations, time from restart to serving, unknown operations after | |
| `compact` | BHMS-Compact over a pty to the native C endpoint, frame sizes; simavr (ATmega328P, 115200 baud) from the AVR container | `sdk/c/tests/host/bhms_host.py` |
| `mcp_compare` | the same action via the MCP bridge (official `mcp` client, stdio) and via the native client | |
| `ts_vs_py` | TypeScript SDK server versus Python SDK server, same conformance-device action | |

Servers: `servers/device_server.py` (N devices; `set_point`, `emit_tick`, `hang`; `--cprofile FILE` profiles it) and
`servers/ping_server.py`. They run in their own processes so client and server never share an event loop (except `gateway*`,
which follow Task 5's in-process design and say so).

`budgets.py` holds the budgets (Ruling R12 revised) and evaluates them; a missing measurement counts as a failure.

## simavr

The ATmega328P run needs the AVR docker image (`sdk/c/scripts/run_avr_on_worker.sh` builds it):
`bench/scripts/simavr_worker.sh 1000 > simavr.json`, then `python bench/run.py --simavr-json simavr.json`.

## Shared machines

`scripts/idle_cpus.py` prints the least busy CPUs for `taskset`. Each scenario records the load average before and after; repeat
a scenario if it changed a lot. Statistics are `bhms bench`'s (nearest-rank percentiles; failures are counted, not hidden).
`compact.py` carries its own five-line percentile because it must run stdlib-only inside the AVR container.
