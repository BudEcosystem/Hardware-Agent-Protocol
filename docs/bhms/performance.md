# BHMS performance

Measured 2026-11-13 against `feat/bhms` at 73974f8 (Python SDK, gateway, TypeScript SDK, C compact library), with the harness in
[`bench/`](../../bench/README.md). Raw JSON for every number below is in `bench/results/`. This document states each budget
(Ruling R12, revised) with its measured number, shows the misses, and says what is and is not known about why.

## Verdict

BHMS is fast enough for its job on the AMD machine and the budgets are met there with thin margins on the durable path; the
durable path is bound by the disk's `fsync`, the non-durable path by CPython, and both scale to the hardware's limit rather
than collapsing. Concretely:

* **Durable invoke is fsync plus about 0.5 ms** when the machine is quiet (1.8 ms against a 1.3 ms fsync). The B1 budget
  (p50 <= fsync + 1 ms) is therefore met with 0.5 ms to spare, and **was missed in 2 of 3 full runs** once the shared host
  was busy (run 1: waitMs=1000 p50 2.47 ms against 2.31 ms; run 3, load 25: both waits). It is a pass only on a quiet machine.
  On the developer workstation (fsync 3.0 ms, slower and loaded CPU) it is a miss by 1 ms.
* **Non-durable invoke** (process mode, or no store at all) is 0.17 to 0.45 ms on the AMD machine: B2 passes with a large
  margin there, and **misses on the workstation** (1.4 to 1.7 ms) where the same Python runs about 6x slower.
* **One fsync per intent caps durable throughput at about 550 operations per second**, however many clients there are
  (100 clients: 555 ops/s, p50 179 ms). Non-durable throughput with 100 clients is 3,600 to 6,100 ops/s. This is the one clear
  scalability gap; group commit (Ruling R12) is the fix and is the first item for 12b.
* The gateway lists 1,000 upstreams / 10,000 devices correctly, pages them in under 25 ms per page over unix and HTTP (p99), and
  starts in 3.2 s. Event fan-in through 1,000 upstream streams runs at 13 to 17 thousand events per second.
* A compact invoke is 35 to 37 bytes on the wire (reply 31 to 34): well inside 64 bytes. Over simavr at 115200 baud the round
  trip is 7.2 ms, of which 6.2 ms is the arithmetic wire time.

## Budgets: pass or fail with the measured number

Primary run: `bench/results/2026-11-13-bmh-worker-amd-run2/` (full sizes, quietest of three). Host `fsync` latency on that
filesystem: **p50 1.30 ms, p99 1.49 ms** (`fdatasync` after appending 600 bytes, 3,000 samples; raw SQLite WAL commit with
`synchronous=FULL` p50 1.51 ms).

| id | budget | run 2 (AMD, load 14) | verdict | run 1 / run 3 (same machine) | workstation (quick sizes) |
|---|---|---|---|---|---|
| B1 | durable invoke p50 <= fsync + 1 ms, p99 <= 5x that (`dispatch`, unix, one client) | waitMs=0: p50 **1.79** vs limit 2.30, p99 3.00 vs 11.51; waitMs=1000: p50 **1.80**, p99 2.95 | **PASS** | run 1 (load 14-18, fsync 1.31): waitMs=0 p50 2.12 PASS; waitMs=1000 p50 **2.47 vs 2.31 FAIL**; p99 pass. Run 3 (load 25, fsync 1.56, limit 2.56): waitMs=0 p50 **3.37 FAIL**, waitMs=1000 p50 **2.70 FAIL**; p99 10.0 / 9.1 vs 12.8 pass | fsync 2.99: p50 **5.05 / 5.02 vs 3.99 FAIL** (2.0 ms above fsync); p99 10.8 / 8.6 vs 19.9 pass |
| B2 | non-durable "process" mode p50 <= 1 ms | process: **0.21** (waitMs=0), **0.26** (waitMs=1000); memory (no store): 0.17 / 0.19 | **PASS** | run 1: 0.33 / 0.36 PASS; run 3 (load 25): 0.38 / 0.45 PASS | process **1.41 / 1.69 FAIL**; memory 1.43 / 1.37 FAIL |
| B3 | gateway with 1,000 upstreams lists correctly | 1,000 upstreams x 10 devices = 10,000 devices, each once and in order, start 3.21 s | **PASS** | PASS in all runs (start 3.2 to 3.4 s) | 100 upstreams (quick): PASS |
| B4 | `devices/list` over 10,000 devices pages in <= 50 ms | unix limit 100: p99 **0.9** ms; limit 500: p99 **9.0** ms; HTTP limit 100: p99 1.9 ms (max 12.1); HTTP limit 500: p99 **22.4** ms | **PASS** | PASS in all runs | unix 500: p99 24.2 ms; HTTP 500: p99 34.2 ms: PASS |
| B5 | compact typical invoke frame <= 64 bytes | request 35 to 37 bytes, reply 31 to 34 bytes (largest 37) | **PASS** | identical | identical |

How B1 and B2 are judged (`bench/budgets.py`): B1 on a fresh server process per cell, one client, an action that returns at
once, 1,000 samples after warm-up, against the `fdatasync` p50 measured in the same run on the same filesystem; B2 on the same
cells with `durability="process"` and with `store=None`. "Lists correctly" (B3) is the gateway reporting every device
(10,000) after start-up, plus the full-catalog paging pass of B4 asserting that every device appears exactly once in sorted
order. Every row of these verdicts is in `budgets.json` of each run directory.

The honest reading of B1: the budget leaves 1.0 ms for everything that is not the disk. CPython needs about 0.5 ms on a
fast core, so the margin is 0.5 ms, and a single contended fsync or a descheduled event loop on a shared host consumes it. On
a slower or busier core the Python overhead alone exceeds 1.0 ms and the budget cannot be met without removing work from the
path (see the proposals). B1 and B2 are CPU-bound budgets stated as if they were disk-bound.

### Variance across the three AMD runs

The machine is shared (load average 12 to 27 on 32 cores; the harness pinned 8 cores each time, but memory bandwidth, the NVMe
and the ext4 journal are shared). Same code, same sizes:

| quantity | run 1 | run 2 | run 3 |
|---|---|---|---|
| load1 around the invoke scenario | 15 to 18 | 14 to 16 | 26 to 27 |
| host fdatasync p50 / p99 (ms) | 1.31 / 2.13 | 1.30 / 1.49 | 1.56 / 5.64 |
| dispatch waitMs=0 p50 / p99 (ms) | 2.12 / 5.03 | 1.79 / 3.00 | 3.37 / 10.01 |
| dispatch waitMs=1000 p50 / p99 (ms) | 2.47 / 5.72 | 1.80 / 2.95 | 2.70 / 9.06 |
| process waitMs=0 p50 (ms) | 0.33 | 0.21 | 0.38 |
| max latency, dispatch (ms) | 213 / 155 | 126 / 17 | 224 / 165 |

Run 1 also includes one harness defect: its `mcp_compare` scenario failed (`CallToolResult` has `is_error` in mcp 2.x, not
`isError`); the harness was fixed before runs 2 and 3. The run-1 directory is kept unedited, as evidence of the variance.

## Environment

AMD machine (`ssh bmh-worker`): AMD RYZEN AI MAX+ PRO 395 (HP Z2 Mini G1a), 32 logical CPUs, 91.8 GB RAM, Ubuntu 26.10, kernel
7.3.0-9, Python 3.12.16, Node v20.20.1 (user-space tarball under `~/hms-lab/node`, 28 MB), `mcp` 2.3.0, websockets 17.4, aiohttp
3.14.5, pydantic 2.14.3. State directory on `/dev/nvme0n1p6` ext4 `rw,relatime` (not tmpfs: the fsync cost is the point). Each
run: `nice -n 10 taskset -c <8 least-busy CPUs>`; the CPU list is in each `environment.json`. Load average is recorded before and
after every measurement (`load1` column); the whole machine was at load 12 to 27 throughout.

Workstation (comparison, no installs): Intel Core i7-10700KF, 16 logical CPUs, Ubuntu 24.04, kernel 7.0.0-42, Python 3.12.3,
Node v20.20.1 (nvm), ext4 `noatime` on NVMe, load 11 to 15 (the desk machine was busy). `--quick` sizes only (100 samples per
latency cell), so percentiles beyond p95 are coarse there.

Sizes: `--full` is 1,000 sequential samples per invoke cell after 200 warm-up, 2,000 to 5,000 operations per concurrency cell,
200 events per fan-out cell, 1,000 upstreams for the gateway. Client and server are separate processes everywhere except the
`gateway*` scenarios, which follow Task 5's benchmark and run the gateway, its in-process light upstreams and the client on one
event loop (so they measure the gateway's CPU cost, not 1,000 real peers).

Percentiles are nearest-rank (`bhms.cli.bench.summarize`, the same code as `bhms bench`). Failures are counted, never dropped:
every cell below had 0 failures.

## Scenarios

`bench/scenarios/`: `fsync`, `transports`, `invoke`, `concurrency`, `gateway` (Task 5's `gateway_scale.py` imported as is),
`gateway_http`, `subscription`, `recovery`, `compact`, `mcp_compare`, `ts_vs_py`. `bench/README.md` describes each. Run:
`python bench/run.py --quick` or `--full`.

## Results (run 2)

Columns are samples, p50, p95, p99, max in milliseconds, operations per second, and the load average at the start and end of the
measurement.

### Host fsync (state directory filesystem)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| fdatasync 600B | 3000 | 1.30 | 1.41 | 1.49 | 35.36 | 745 | 12.3->14.1 |
| fsync 600B | 3000 | 1.30 | 1.41 | 1.50 | 14.79 | 746 | 12.3->14.1 |
| fdatasync 4096B | 3000 | 1.31 | 1.41 | 1.50 | 9.21 | 741 | 12.3->14.1 |
| fsync 4096B | 3000 | 1.40 | 2.02 | 3.20 | 8.85 | 681 | 12.3->14.1 |

SQLite WAL commit (600 B row): NORMAL p50 0.0042 ms / p99 0.0134; FULL p50 1.505 ms / p99 4.6154.

### Transports, ping only

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix sequential | 5000 | 0.05 | 0.08 | 0.09 | 1.24 | 18194 | 14.1->14.1 |
| tcp sequential | 5000 | 0.06 | 0.09 | 0.12 | 3.15 | 14952 | 14.1->15.8 |
| websocket sequential | 5000 | 0.11 | 0.14 | 0.16 | 3.37 | 9041 | 15.8->15.8 |
| stdio sequential | 5000 | 0.06 | 0.09 | 0.14 | 2.90 | 16321 | 15.8->15.8 |

Pipelined (256 in flight): unix 33651/s, tcp 27589/s, websocket 30833/s, stdio 90987/s

### `actions/invoke`, one client, sequential

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix/full/waitMs=0 | 1000 | 3.21 | 3.81 | 4.59 | 21.32 | 302 | 15.8->15.4 |
| unix/full/waitMs=1000 | 1000 | 3.18 | 3.55 | 4.38 | 18.27 | 307 | 15.4->14.8 |
| unix/dispatch/waitMs=0 | 1000 | 1.79 | 2.01 | 3.00 | 125.57 | 506 | 14.8->14.1 |
| unix/dispatch/waitMs=1000 | 1000 | 1.80 | 2.12 | 2.95 | 17.47 | 535 | 14.1->14.1 |
| unix/process/waitMs=0 | 1000 | 0.21 | 0.39 | 0.51 | 17.45 | 3881 | 14.1->14.1 |
| unix/process/waitMs=1000 | 1000 | 0.26 | 0.46 | 0.59 | 15.96 | 3232 | 14.1->14.1 |
| unix/memory/waitMs=0 | 1000 | 0.17 | 0.31 | 0.45 | 15.23 | 4709 | 13.8->13.8 |
| unix/memory/waitMs=1000 | 1000 | 0.19 | 0.36 | 0.52 | 18.15 | 4223 | 13.8->13.8 |
| ws/dispatch/waitMs=0 | 1000 | 1.86 | 2.31 | 2.97 | 19.39 | 516 | 13.8->13.8 |
| ws/dispatch/waitMs=1000 | 1000 | 1.89 | 2.46 | 3.12 | 125.72 | 466 | 13.8->13.9 |
| ws/memory/waitMs=0 | 1000 | 0.31 | 0.48 | 0.56 | 31.23 | 2787 | 13.9->13.9 |
| ws/memory/waitMs=1000 | 1000 | 0.32 | 0.48 | 0.58 | 31.84 | 2672 | 13.9->13.9 |
| stdio/dispatch/waitMs=0 | 1000 | 2.05 | 2.61 | 3.37 | 168.07 | 440 | 13.9->14.0 |
| stdio/dispatch/waitMs=1000 | 1000 | 1.97 | 2.96 | 4.70 | 125.27 | 388 | 14.0->14.0 |
| stdio/memory/waitMs=0 | 1000 | 0.17 | 0.29 | 0.43 | 14.61 | 4993 | 14.0->14.0 |
| stdio/memory/waitMs=1000 | 1000 | 0.19 | 0.29 | 0.41 | 22.78 | 4446 | 13.5->13.5 |

### Concurrent clients (`waitMs=1000`, unix)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| dispatch/same-device/1 | 2000 | 1.83 | 2.18 | 3.08 | 201.49 | 466 | 13.5->13.1 |
| dispatch/same-device/10 | 2000 | 17.16 | 20.67 | 26.10 | 35.57 | 564 | 13.1->13.1 |
| dispatch/same-device/100 | 2000 | 178.51 | 187.26 | 188.41 | 199.08 | 555 | 13.2->13.1 |
| dispatch/spread/10 | 2000 | 16.26 | 17.71 | 24.28 | 32.92 | 604 | 13.1->13.1 |
| dispatch/spread/100 | 2000 | 167.03 | 176.77 | 474.75 | 481.90 | 546 | 12.7->12.7 |
| process/same-device/1 | 5000 | 0.24 | 0.40 | 0.53 | 44.81 | 3539 | 12.8->12.8 |
| process/same-device/10 | 5000 | 2.04 | 2.35 | 3.08 | 22.35 | 4739 | 12.8->12.8 |
| process/same-device/100 | 5000 | 27.15 | 30.20 | 33.82 | 39.94 | 3641 | 12.8->12.8 |
| process/spread/10 | 5000 | 1.56 | 2.17 | 2.63 | 27.31 | 5990 | 12.8->12.8 |
| process/spread/100 | 5000 | 14.90 | 21.32 | 51.36 | 52.32 | 6110 | 12.8->12.8 |

### Gateway, 1000 upstreams x 10 devices (in-process upstreams)

start 3.21 s, background validation 2.69 s, RSS +220.6 MB; devices 10000.

| paging | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|---:|
| limit_100_ms | 100 | 0.636 | 0.669 | 0.689 | 0.689 |
| limit_500_ms | 20 | 3.352 | 10.653 | 10.653 | 10.653 |

Event fan-in: 5000 events from 1000 upstream streams in 0.374 s = 13370/s; latency under the burst p50 314.921 / p99 361.373 / max 362.495 ms; +5.8 MB.

| invoke via | n | p50 ms | p95 ms | p99 ms | max ms | overhead p50 ms |
|---|---:|---:|---:|---:|---:|---:|
| direct_wait0 | 1000 | 0.188 | 0.283 | 0.334 | 9.37 | - |
| direct_wait1000 | 1000 | 0.211 | 0.329 | 0.394 | 1.078 | - |
| gateway_process_wait0 | 1000 | 0.531 | 0.831 | 0.943 | 2.046 | 0.343 |
| gateway_process_wait1000 | 1000 | 0.6 | 0.695 | 0.878 | 1.324 | 0.389 |
| gateway_dispatch_wait0 | 1000 | 2.262 | 3.007 | 4.654 | 11.128 | 2.074 |
| gateway_dispatch_wait1000 | 1000 | 2.385 | 3.214 | 4.469 | 10.557 | 2.174 |

### Gateway over unix versus Streamable HTTP (10001 devices)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix devices_list_limit_100 | 303 | 0.66 | 0.76 | 0.91 | 0.92 | 1496 | 12.8->12.8 |
| unix devices_list_limit_500 | 63 | 3.59 | 5.91 | 9.02 | 9.02 | 266 | 12.8->12.8 |
| unix invoke_waitMs_0 | 500 | 0.45 | 0.52 | 0.56 | 0.98 | 2174 | 12.8->12.8 |
| unix invoke_waitMs_1000 | 500 | 0.54 | 0.61 | 0.67 | 1.25 | 1822 | 12.8->12.8 |
| http devices_list_limit_100 | 303 | 0.96 | 1.28 | 1.86 | 12.13 | 943 | 12.8->13.6 |
| http devices_list_limit_500 | 63 | 5.41 | 7.33 | 22.44 | 22.44 | 166 | 12.8->13.6 |
| http invoke_waitMs_0 | 500 | 0.80 | 0.97 | 1.32 | 1.60 | 1203 | 12.8->13.6 |
| http invoke_waitMs_1000 | 500 | 0.89 | 1.11 | 1.55 | 22.70 | 1028 | 12.8->13.6 |

### Subscription fan-out (1 event stream to N listeners)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| listeners=1 delivery | 200 | 1.91 | 2.22 | 3.01 | 3.73 | 511 | 13.6->13.6 |
| listeners=1 slowest listener | 200 | 1.91 | 2.22 | 3.01 | 3.73 | 511 | 13.6->13.6 |
| listeners=10 delivery | 2000 | 2.09 | 2.91 | 3.58 | 84.98 | 3802 | 13.6->13.6 |
| listeners=10 slowest listener | 200 | 2.14 | 2.95 | 3.59 | 84.98 | 380 | 13.6->13.6 |
| listeners=50 delivery | 10000 | 2.85 | 5.27 | 6.31 | 10.91 | 13772 | 13.6->13.6 |
| listeners=50 slowest listener | 200 | 3.04 | 5.59 | 6.54 | 10.91 | 275 | 13.6->13.6 |
| listeners=100 delivery | 20000 | 5.07 | 7.54 | 8.77 | 62.33 | 15970 | 13.6->13.6 |
| listeners=100 slowest listener | 200 | 5.91 | 8.29 | 9.13 | 62.33 | 160 | 13.6->13.6 |

Deliveries lost: listeners=1: 0, listeners=10: 0, listeners=50: 0, listeners=100: 0

### Crash recovery (SIGKILL, restart)

| case | journal bytes | to ready s | to first response s | unknown after |
|---|---:|---:|---:|---:|
| devices=1000 unknown=0 | 9136512 | 0.725 | 0.726 | 0 |
| devices=10 unknown=10 | 514816 | 0.18 | 0.181 | 10 |
| devices=100 unknown=100 | 4329936 | 0.232 | 0.233 | 100 |
| devices=1000 unknown=1000 | 48245720 | 0.758 | 0.759 | 1000 |

### BHMS-Compact

| target | op | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---:|---:|---:|---:|---:|
| native | invoke | 3000 | 0.042 | 0.0576 | 0.0714 | 0.9542 |
| native | read | 1500 | 0.0424 | 0.06 | 0.0775 | 1.2897 |
| simavr | invoke | 1000 | 7.1643 | 7.3202 | 8.8826 | 11.9772 |
| simavr | read | 500 | 7.1948 | 7.5883 | 8.3569 | 9.9004 |

native: invoke request [35, 36, 37] bytes, reply [31, 32, 34], read frames [29, 30, 31, 40, 41, 42, 43], hello 48;

simavr: invoke request [35, 36, 37] bytes, reply [31, 32, 34], read frames [29, 30, 40, 41, 42], hello 48; wire floor 6.163 ms at 115200 baud, p50 over floor 1.001 ms;

### MCP bridge versus native client

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| native | 1000 | 1.82 | 2.15 | 3.11 | 87.56 | 506 | 13.6->13.6 |
| mcp_bridge | 1000 | 3.08 | 4.99 | 5.97 | 11.33 | 297 | 13.6->14.1 |

Bridge overhead p50 1.267 ms; tool result text 82 bytes; `tools/list` 1.343 ms.

### TypeScript SDK server versus Python SDK server (`axis-1.pulse`, `waitMs=1000`, unix)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| python/durable | 1000 | 6.53 | 20.95 | 26.66 | 177.22 | 113 | 14.1->19.7 |
| typescript/durable | 1000 | 11.07 | 17.58 | 22.94 | 140.50 | 85 | 19.7->25.9 |
| python/memory | 1000 | 1.89 | 3.63 | 4.89 | 38.81 | 469 | 25.9->25.5 |
| typescript/memory | 1000 | 2.15 | 4.75 | 6.61 | 8.56 | 414 | 25.5->25.5 |

## Workstation comparison (quick sizes, load 11 to 15)

Budget verdicts on the developer workstation (i7-10700KF, host fsync p50 2.99 ms). Quick sizes mean 100 samples per latency cell and
100 upstreams for the gateway (B3 reads "100 upstreams" there). All other workstation tables are in
`bench/results/2026-11-13-workstation-quick/`.

| verdict | budget | measured | limit |
|---|---|---|---|
| **FAIL** | B1 durable invoke (dispatch, unix, waitMs=0) p50 | 5.05 ms | <= 3.99 ms (fsync p50 2.99 + 1) ; overhead above fsync: 2.06 ms |
| PASS | B1 durable invoke (dispatch, unix, waitMs=0) p99 | 10.81 ms | <= 19.93 ms (5 x 3.99) ; host fsync p99 is 8.44 ms |
| **FAIL** | B1 durable invoke (dispatch, unix, waitMs=1000) p50 | 5.02 ms | <= 3.99 ms (fsync p50 2.99 + 1) ; overhead above fsync: 2.03 ms |
| PASS | B1 durable invoke (dispatch, unix, waitMs=1000) p99 | 8.56 ms | <= 19.93 ms (5 x 3.99) ; host fsync p99 is 8.44 ms |
| **FAIL** | B2 non-durable invoke (process, unix, waitMs=0) p50 | 1.41 ms | <= 1.00 ms |
| **FAIL** | B2 non-durable invoke (process, unix, waitMs=1000) p50 | 1.69 ms | <= 1.00 ms |
| **FAIL** | B2 non-durable invoke (memory, unix, waitMs=0) p50 | 1.43 ms | <= 1.00 ms |
| **FAIL** | B2 non-durable invoke (memory, unix, waitMs=1000) p50 | 1.37 ms | <= 1.00 ms |
| PASS | B3 gateway lists 100 upstreams correctly | 1000 devices, start 0.73 s | 1000 devices, each once, in order ; ordering and uniqueness are asserted by the gateway test suite and by B4's paging pass |
| PASS | B4 devices/list 10,000 devices (unix, limit 100) per page | p99 3.7 ms, max 4.4 ms, p50 2.3 ms | <= 50 ms (p99), complete and ordered ; every device listed once in order: True |
| PASS | B4 devices/list 10,000 devices (unix, limit 500) per page | p99 24.2 ms, max 24.2 ms, p50 8.9 ms | <= 50 ms (p99), complete and ordered ; every device listed once in order: True |
| PASS | B4 devices/list 10,000 devices (http, limit 100) per page | p99 5.0 ms, max 12.1 ms, p50 3.1 ms | <= 50 ms (p99), complete and ordered ; every device listed once in order: True |
| PASS | B4 devices/list 10,000 devices (http, limit 500) per page | p99 34.2 ms, max 34.2 ms, p50 15.9 ms | <= 50 ms (p99), complete and ordered ; every device listed once in order: True |
| PASS | B4 devices/list 10,000 devices (gateway_scale, unix, limit 100) per page | p99 4.6 ms, max 4.6 ms, p50 3.4 ms | <= 50 ms (p99) |
| PASS | B4 devices/list 10,000 devices (gateway_scale, unix, limit 500) per page | p99 18.4 ms, max 18.4 ms, p50 16.3 ms | <= 50 ms (p99) |
| PASS | B5 compact typical invoke frame (native pty) | 37 bytes (request [35, 36, 37], reply [31, 32, 34]) | <= 64 bytes |


## What the numbers say

* **Transports are not the cost.** Bare ping round trip is 0.05 ms (unix), 0.06 (tcp, stdio), 0.11 (websocket); pipelined
  throughput 28 to 91 thousand requests per second. A non-durable invoke (0.17 to 0.26 ms) is a few times a ping, and the
  durable invoke is the same across unix, websocket and stdio (1.79, 1.86, 2.05 ms): durability dominates, transport does not.
* **Durability costs one fsync per fsync.** `full` (synchronous=FULL everywhere) 3.2 ms; `dispatch` (one barrier on the
  intent) 1.8 ms; `process` 0.21 ms; `memory` 0.17 ms. That is `fsyncs x 1.3 ms + 0.2 to 0.5 ms`. `dispatch` is already
  the minimum for "intent durable before dispatch" without batching.
* **Concurrency.** Durable throughput is flat at 470 to 600 ops/s from 1 client to 100 (same device or spread over 100
  devices): the single journal serialises one fsync per intent, so latency grows linearly with clients (p50 1.8 ms at 1, 17 ms at
  10, 179 ms at 100). Non-durable throughput scales until CPython's single event loop saturates: 3.5 to 4.7 thousand ops/s
  on one device, 6.0 to 6.1 thousand ops/s spread over 100 devices; p50 at 100 clients is 15 to 27 ms.
* **Gateway.** Over a process-mode journal the gateway adds 0.34 ms (waitMs=0) and 0.39 ms (waitMs=1000) to a direct
  invoke (0.19 to 0.21 ms). With the default `dispatch` journal it adds **2.07 / 2.17 ms**: the gateway writes a
  pending-forward row with a barrier commit before sending (`gateway/journal.py`, `pending_put`), i.e. one fsync per forwarded
  invoke. (Task 5's report says the gateway needs no barrier; the code has one. In front of a durable device server this is two
  fsyncs per invoke end to end; that combination was not measured, see below.) Streamable HTTP adds 0.35 ms per invoke and
  0.3 ms (limit 100) to 1.8 ms (limit 500) per `devices/list` page over the unix socket.
* **Subscription fan-out** is linear and cheap: delivery latency (invoke to listener parse) p50 1.9 ms with 1 listener, 2.1 ms
  with 10, 2.9 ms with 50 and 5.1 ms with 100 (p99 8.8 ms): about 0.03 ms per listener; no delivery lost in any cell.
* **Crash recovery** is not the slow part of a restart. SIGKILL with 1,000 running operations on 1,000 devices, restart to first
  response: 0.76 s against 0.73 s with no operations, so settling 1,000 operations to `unknown` costs about 30 ms. The
  constant part is interpreter start, imports and declaring the devices (0.18 s for 10 devices). All N operations were
  reported `unknown` afterwards (nothing lost, nothing invented). The journal holds 48 MB (database plus its
  uncheckpointed WAL) after 1,000 invokes on top of a 9 MB baseline, about 39 KB written per operation; this is the WAL's page-granular
  write amplification, and part of why disk time per invoke is what it is.
* **Compact binding.** Native C endpoint over a pty: 0.042 ms p50 per invoke (0.041 to 0.042 over three runs). ATmega328P in
  simavr, 115200 baud: 7.16 ms p50 per invoke and 7.19 ms per read, against a 6.16 ms wire-time floor for the 35-byte request
  and 34-byte reply actually exchanged (10 bits per byte): the device and host add about 1.0 ms; the rest is the serial line.
* **MCP versus native.** The MCP bridge (official `mcp` 2.3 client over stdio to `python -m bhms mcp`) takes 3.08 ms p50
  against 1.82 ms native for the same durable action (+1.27 ms; run 3: 2.88 vs 1.80, +1.08 ms): an extra process hop, MCP
  framing both ways, argument validation and rendering. The agent receives 82 bytes of result text; `tools/list` is 1.3 ms.
* **TypeScript versus Python server.** Same conformance-device action (`axis-1.pulse`, which itself holds 1 ms): without a store
  they are equal (1.40 ms both in run 1; 1.62 vs 1.46 in run 3). With the default durable store the TypeScript server is about
  1.4x slower (run 1: 3.92 Python, 5.68 TypeScript; run 3: 4.22 vs 5.72). Run 2's durable cell ran while the host load climbed from
  14 to 26 (python 6.5, typescript 11.1) and is not comparable. The TypeScript journal fsyncs every operation record
  (`store.ts` `writeOp` -> `append(..., true)`: accepted, dispatching, completed), where the Python server issues one barrier on the
  intent; that is consistent with the gap.

## Profiles of the misses

All profiles: `bench/results/2026-11-13-bmh-worker-profiles/`, produced by `bench/scripts/profile_invoke.py` on the AMD machine
(durable `dispatch`, `waitMs=1000`, 3,000 and 6,000 sequential invokes). cProfile inflates everything about 25% here (2.30 ms
per invoke under profile against 1.8 unprofiled); read shares, not times. py-spy could not attach to a sibling process
(`ptrace_scope=1`), so the server was started under `py-spy record` (500 Hz); py-spy drops idle samples, and a thread blocked in
`fsync` with the GIL released counts as idle, so its shares exclude the disk wait: use it for the CPU picture only.

### B1 (durable invoke above fsync): where the extra 0.5 ms goes

Server, cProfile, per invoke:
* SQLite `Connection.execute`: 5.40 s of 7.72 s total own time (70%): 39,652 calls for 3,300 invokes, **12 statements, 8
  `Store.transaction` contexts and 4 commits per invoke**.
* `Journal.create` (admission: the barrier commit of the intent) 5.37 s cumulative = **1.63 ms per invoke** against 1.50 ms for
  a bare SQLite FULL commit measured on the same disk (unprofiled) and 1.30 ms for a bare fdatasync: indicatively the intent commit
  is about 0.13 ms above the SQLite floor and 0.33 ms above the fsync floor (the profiled figure is inflated).
* Completion (`Executor._complete` -> `Journal.transition`, a NORMAL commit): 0.31 s = 0.09 ms. Argument admission (jsonschema)
  0.158 s = 0.048 ms. Canonical JSON and digests 0.118 s = 0.036 ms. asyncio scheduling and socket calls: the rest.

py-spy top server frames (CPU only): `Store.transaction` store.py:213 (the `COMMIT` execute) 11.0%, `Store._write` store.py:246
4.4%, `EpollSelector.select` 3.7%, `Store._set_sync` store.py:163 (the `PRAGMA synchronous` toggles around each barrier) 2.1%,
`create_task` 1.8% + 0.6%, pydantic `model_validate` 1.6%, `operations.iso` 2.0% (two lines). Inclusive: `Executor.admit` 11.8% +
9.0%, `Journal.transition` 17.8%, `Session._run_request` 48.9%.

Client, cProfile, 3,000 calls: 0.73 s non-idle (0.24 ms per call). **`to_wire` builds a new `TypeAdapter(Any)` on every call**
(`protocol/types/_base.py:60`; `pydantic.TypeAdapter.__init__` 0.171 s cumulative = 57 microseconds per call, 24% of the
client's own work). Next: `model_validate` 0.10 s, `to_camel` 0.084 s, `Session.request` 0.083 s.

Summary: durable `dispatch` p50 = 1.30 ms fsync + about 0.2 ms SQLite commit overhead above the fsync + about 0.2 ms server
Python + about 0.15 ms client Python + socket and scheduling. The remaining improvable Python work totals 0.1 to 0.2 ms; the
fsync and the commit are fixed per intent unless intents are batched. B1 is therefore met on a quiet fast machine and cannot be
met reliably on a slow or busy one.

### B2 (non-durable p50 <= 1 ms): passes on AMD, misses on the workstation

On the AMD machine process-mode p50 is 0.21 to 0.45 ms (3 runs): a pass. The workstation misses (1.41 / 1.69 ms) because
the same code is about 6x slower per call on a loaded i7: it is a statement about the budget's hardware dependence, not a
different code path. The profile above (client 0.24 ms of Python per call, server about 0.2 ms) is why a 1 ms budget cannot be
promised on every CPU.

### Tail latency: the 100+ ms maxima

The max of durable cells is 100 to 250 ms in almost every run (e.g. 125 ms, 168 ms, 213 ms), against a raw fsync max of 9 to 35 ms.
`bench/scripts/tail_experiment.py` (3 rounds x 8,000 invokes x 3 variants, `tail_experiment.txt`) separates the causes:

* **A one-time generation-2 garbage collection in the server accounts for the stall near invoke #700**: with a GC callback
  logging pauses, every server run logged one gen-2 collection of 42 to 81 ms that freed about 29,000 objects (and a 20 to 37 ms
  one earlier, at start-up). With `gc.freeze()` after start-up (what `Gateway.serve` already does) that collection falls to 11 to 25 ms and
  the stall at index ~492 disappears from the first-slow-index list in all three rounds.
* The background WAL checkpointer is **not** the cause: with it effectively disabled the 100+ ms maxima remain (110, 203, 121
  ms).
* Rare 100 to 250 ms stalls remain in every variant including `gc.freeze` (max 123, 108 ms). They are not GC, not the
  checkpointer, and not seen in a 3,000-sample raw fsync probe (max 35 ms); most likely the shared filesystem or the machine.
  **Cause not established.**

p99 is unaffected (3.5 to 5 ms in all variants); 6 to 12 samples in 8,000 exceed 10 ms.

## Proposals for 12b (ordered by expected gain)

1. **Group commit for concurrent intents (Ruling R12).** Evidence: durable throughput is 470 to 600 ops/s at 1, 10 and 100
   clients (one fsync per intent); process mode does 3,500 to 6,100 ops/s with the same code. A commit window shared by every intent
   admitted while the previous fsync runs should lift durable throughput with 100 clients on distinct devices from about 550
   toward the process-mode ceiling (4,000 to 6,000 ops/s: roughly 7x to 11x) and cut p50 at 100 clients from 167 to 179 ms to about
   15 to 30 ms. A single sequential client is unchanged (still one fsync, 1.8 ms). Caveat: operations on the *same* device execute
   one at a time and each needs its own intent durable before dispatch, so the same-device case stays near 550 ops/s unless intents of
   queued operations are made durable while the previous one runs (a semantic change: such an operation would recover as
   `unknown` instead of `rejected`); decide that explicitly.
2. **`gc.collect(); gc.freeze()` after start-up in `DeviceServer.serve`/`listen`**, as `Gateway.serve` does. Evidence above: it
   removes the 40 to 80 ms generation-2 pause (to 11 to 25 ms). Expected: p99.9 and max improve by tens of ms; no p50 change. One
   line plus a test.
3. **Cache the `TypeAdapter(Any)` in `to_wire`** (`protocol/types/_base.py:60`; a module-level constant). Evidence: 57 microseconds
   per call under cProfile, 24% of client work. Expected: 0.02 to 0.05 ms off every client call (also off the gateway, which
   serialises through the same path); helps B2 more than B1.
4. **Fewer SQLite statements per invoke** (12 statements, 8 transactions, 4 commits today): fold the accept and dispatch
   transactions and the `PRAGMA synchronous` toggles (`Store._set_sync`, 2.1% of CPU) into one barrier transaction by keeping a
   second connection permanently at `synchronous=FULL` for barrier commits. Expected: 0.05 to 0.1 ms per invoke (about 5% of the
   durable p50, 25 to 40% of the non-fsync part); combines naturally with item 1.
5. **Decide the gateway's barrier.** The gateway adds 2.07 ms in `dispatch` mode because of the pending-forward barrier, and the
   Task 5 report says none is needed. If a durable device sits behind it the intent is already durable at the device; dropping
   the gateway barrier (keyed retry already reconciles, per the Task 5 design note) would take 2.07 ms to about 0.35 ms per invoke.
   If it must stay, group commit (item 1) applies to it as well. Needs a spec decision, not just code.
6. **TypeScript server: fsync only the intent.** `writeOp` fsyncs every operation record. Syncing only the `dispatching` record
   (as Python does) removes about two fsyncs per invoke: expected TypeScript durable p50 from about 5.7 ms toward 3 ms in the
   same harness (below the Python server).
7. **Native transport path** (uvloop, or batching `send`) is the only way to take much more than 0.1 ms off the non-durable
   path; per the profile the remaining Python is spread thinly across session, dispatch and validation, with no single hot frame.
   Not recommended before 1 to 4.

## Not measured, and why

* **Gateway with a durable journal in front of a durable device server** end to end (expected about two fsyncs per invoke):
  the `overhead` scenario uses a non-durable upstream so as to isolate the gateway; the combined cell was not added.
* **1,000 real upstream connections.** The 1,000-upstream numbers use Task 5's in-process light upstreams on one event loop
  (the gateway's CPU and memory cost, not socket and scheduler cost of 1,000 peers).
* **TCP with a token.** `DeviceServer` refuses TCP (no credential on TCP), so TCP is measured only at the bare JSON-RPC level
  (ping). Streamable HTTP exists only in the gateway, so it is measured through the gateway.
* **Clients beyond 100, large payloads, long soak runs, memory per connection** (except the gateway's RSS), and any run with the
  sanitizer builds: not attempted in this pass.
* **ATmega2560 and real serial hardware**: only ATmega328P in simavr (the simulated UART honours baud timing; real USB-serial
  adapters add their own latency timer, typically 1 to 16 ms, which is not in these numbers).
* **TypeScript client.** Only the TypeScript *server* is compared (driven by the Python client).
* **Power-loss behaviour of the disk**: fsync of 1.3 ms on this NVMe suggests the flush is honoured, but it was not tested by
  pulling power; the budget is stated relative to the fsync the host reports.
* **py-spy attach** was refused by the kernel (`ptrace_scope=1`); worked around by launching the server under py-spy, which
  excludes fsync wait from its shares.

## Reproduce

```
pip install -e 'sdk/python[http,mcp]' py-spy
(cd sdk/typescript && npm ci && npx tsc)
python bench/scripts/idle_cpus.py 8 5                       # pick quiet CPUs on a shared box
BENCH_DIR=~/hms-lab/bench-state nice -n 10 taskset -c <cpus> \
  python bench/run.py --full --label amd --cpus <cpus> --node ~/hms-lab/node/bin/node --simavr-json simavr.json
bench/scripts/simavr_worker.sh 1000 > simavr.json            # needs the bhms9a-avr docker image
python bench/tables.py bench/results/<dir>                   # Markdown tables
python bench/scripts/profile_invoke.py --out DIR [--pyspy]   # profiles
python bench/scripts/tail_experiment.py                      # GC / checkpointer tail attribution
```

Result directories: `2026-11-13-bmh-worker-amd-run1` (load 14 to 18, mcp scenario failed on a harness defect since fixed),
`...-run2` (primary), `...-run3` (load 25 at the start), `2026-11-13-workstation-quick`, `2026-11-13-bmh-worker-profiles`.
