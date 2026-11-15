# BHMS performance

Measured 2026-11-13 (Task 12a, the "before" record, revised after review) against `feat/bhms` at 73974f8, and again on 2026-11-14/15
(Task 12b, before and after its SDK changes, base `f60771b`), with the harness in [`bench/`](../../bench/README.md). Raw JSON for
every number below is in `bench/results/`. This document states each budget (Ruling R12, revised) with its measured number, shows
the misses, and says what is and is not known about why. The first part is Task 12b; everything from "Task 12a verdict" on is the
Task 12a record, unchanged except for this heading.

## Task 12b: after the performance changes (before and after)

Task 12b (feat/bhms `f60771b..`) changed the SDKs as the Task 12a proposals said and re-ran the same harness. The "before" numbers
in this part are **not** the 12a runs: they are the base commit `f60771b` measured again on the AMD machine in the same sessions,
interleaved with the "after" runs (`before<N>` then `after<N>`, same scenarios, same pinning procedure), so that both sides saw the
same host. Raw JSON and samples: `bench/results/2026-11-14-bmh-worker-12b-*`, `2026-11-15-bmh-worker-12b-*` and
`2026-11-14-workstation-12b-*`. The Task 12a record follows unchanged below this part.

What changed (see the Task 12b report for the tests and commits):

* **Group commit (Ruling R12).** A barrier is a commit at `synchronous=NORMAL` plus an `fdatasync` of the WAL (what SQLite's FULL
  adds in WAL mode); the connection never switches safety level. Concurrent intents share one `fdatasync` in the store's sync
  thread while the event loop keeps serving; an intent with nobody to share with (one client, or operations queued on one device)
  is synced on the event loop thread, as before, with no thread hand-off. No handler runs, and no invoke is answered, before the
  `fdatasync` covering its own `dispatching` record has returned.
* **Hot paths.** `to_wire` no longer builds a `TypeAdapter` per call; an invoke is 8 SQL statements and 2 commits instead of 11
  and 2 (no `PRAGMA synchronous` toggles, one INSERT for all history entries of a commit); `DeviceServer.serve` freezes its
  start-up heap (`gc.collect(); gc.freeze()`, as `Gateway.serve` did).
* **Gateway pending-forward barrier: kept**, now a shared (group-committed) barrier; the decision and its reason are in the spec
  (06 BHMS-OPS-003, 07 §7.6) and below.
* **TypeScript journal:** one `fsync` per invoke (the `dispatching` record) instead of three.
* **Fix round 2 (Ruling R57):** a queued operation's `accepted` record is a (group-committed) barrier too, durable before it is
  answered or observed, in both SDKs; an operation once visible stays visible as its last durable state. This adds one
  shared sync per queued operation; the one-client path is unchanged. Measured on the workstation (quick sizes, two
  interleaved pairs, `2026-11-16-workstation-12b-fix2-*`): same device with 10 / 100 clients 218-219 / 199-217/s before,
  208-215 / 190-214/s after (the queued `accepted` syncs of concurrent admissions are shared); spread over devices
  223-244 / 241-255/s before, 711-815 / 1,326-1,452/s after. The AMD pair run for it (`2026-11-16-bmh-worker-12b-*17`)
  met load 53 to 74 and is not comparable (the base's concurrency warm-up failed there).
* **Fix round 1 (Ruling R47):** an operation written behind a deferred barrier is not observable (notifications held and
  released in order, not in `operations/get`/`operations/list`) until its sync has completed; the B1 pairs 13 to 16 and
  `cont8` ran this code. (The TypeScript server fsyncs the `dispatching` record synchronously before notifying, so it already
  behaved so.)

### Budgets, before and after (AMD machine)

| id | budget | before (`f60771b`, same sessions) | after (12b) | verdict after |
|---|---|---|---|---|
| B1 | durable invoke p50 <= floor + 1 ms, p99 <= 5x | 8 of 13 runs pass (7 of 8 before fix round 1); quiet host p50 1.70 to 1.80 ms, p99 2.7 to 3.0 ms | 8 of 15 runs pass (7 of 10 before fix round 1); quiet host p50 **1.69 to 1.78 ms**, p99 2.3 to 2.9 ms; misses at load 12 to 84, where the base misses too | **FAIL** (aggregate; see below) |
| B2 | non-durable p50 <= 1 ms | 8 of 8 pass (process 0.19 to 0.24 ms) | 10 of 10 pass (process 0.18 to 0.32 ms, memory 0.14 to 0.25 ms) | **PASS** |
| B3 | gateway lists 1,000 upstreams correctly | PASS (12a) | PASS: 10,000 listed, unique, ordered, equal to the expected ids | **PASS** |
| B4 | `devices/list` of 10,000 devices <= 50 ms per page | PASS (12a: worst p99 26 ms) | PASS: worst p99 15.4 ms (HTTP, limit 500; unix 7.4 ms) | **PASS** |
| B5 | compact typical invoke frame <= 64 B | PASS (35 to 37 B) | PASS: request 35 to 37 B, reply 31 to 34 B | **PASS** |

#### B1 across runs (`bench/aggregate.py`, all AMD runs of this task)

| run | code | load1 (invoke) | fdatasync p50 | dispatch w0 p50 / p99 | dispatch w1000 p50 / p99 | B1 |
|---|---|---|---:|---|---|---|
| before5 / after5 | base / 12b (first policy) | 3-2 / 2-2 | 1.30 / 1.30 | 1.80 / 2.81 vs **1.70 / 2.88** | 1.80 / 2.91 vs **1.70 / 2.73** | PASS / PASS |
| before6 / after6 | base / 12b (first policy) | 2-3 / 4-6 | 1.30 / 1.30 | 1.73 / 3.00 vs 2.20 / 4.37 | 1.78 / 2.84 vs 2.03 / 4.59 | PASS / PASS |
| before7 / after7 | base / 12b (first policy) | 7-10 / 12-14 | 1.40 / 1.41 | 1.99 / 35.52 vs 2.20 / 33.47 | 2.94 / 35.43 vs 2.14 / 4.71 | FAIL / FAIL |
| before8 / after8 | base / 12b | 22-24 / 18-16 | 1.31 / 1.41 | 1.93 / 4.60 vs **1.71 / 2.89** | 1.85 / 3.46 vs **1.71 / 2.91** | PASS / PASS |
| before9 / after9 | base / 12b | 14-14 / 16-17 | 1.30 / 1.30 | 1.78 / 2.98 vs 2.18 / 5.16 | 1.78 / 2.99 vs 1.79 / 2.99 | PASS / PASS |
| before10 / after10 | base / 12b | 14-15 / **26-33** | 1.30 / 1.39 | 1.77 / 3.01 vs 4.18 / 10.92 | 1.78 / 3.00 vs 4.59 / 12.78 | PASS / FAIL |
| before11 / after11 | base / 12b | 3-4 / 4-4 | 1.30 / 1.30 | 1.71 / 3.01 vs **1.69 / 2.62** | 1.72 / 2.91 vs **1.70 / 2.75** | PASS / PASS |
| before12 / after12 | base / 12b | 5-5 / 4-4 | 1.30 / 1.30 | 1.70 / 2.69 vs **1.70 / 2.67** | 1.73 / 2.92 vs **1.70 / 2.31** | PASS / PASS |
| after-full2 | 12b | **28-36** | 1.40 | 2.63 / 9.48 | 3.05 / 8.52 | FAIL |
| after-full3 | 12b | 5-4 | 1.30 | **1.69 / 3.04** | **1.78 / 2.71** | PASS |
| before13..16, cont8 / after13..16, cont8 | base / 12b with R47 (fix round 1) | 20 to 84 | 1.30 to 3.00 | see the paired table | | before: 1 of 5 pass; after: 1 of 5 pass |

"First policy" is the 12b code before commit `03140b0` (a lone intent was synced inline only when the server had one request in
flight); it differs from the final code only for concurrent same-device work, not for these one-client cells.

* **B1 aggregate: FAIL.** With the final code 5 of 7 runs pass (after8, 9, 11, 12 and the full run after-full3); over every 12b run 7 of 10
  (fix round 1 added after13 to after16 and after-cont8: after15 passes, the others ran at load 25 to 84 and fail).
  Every miss is at a host load the passing runs did not see: `after10` (load 26 to 33) and
  `after-full2` (28 to 36) miss the p50 by CPU contention (the process-mode p50 rose too, 0.18 -> 0.32 ms); `before7` and `after7`
  miss the p99 with 33 to 36 ms tails that the raw `fdatasync` probe of the same run shows as well (`fsync 600B` p99 32 ms, 86
  samples over 10 ms in `before7`; `fdatasync 4096B` p99 33 ms, 136 over 10 ms in `after7`): a shared-NVMe episode, not BHMS.
  The base code fails 1 of 8 in those sessions; it also fails at the loads where 12b failed once it ran there (fix round 1,
  below).

**All paired runs** (each `before<N>` ran right before `after<N>` on the same CPUs; dispatch p50 waitMs 0 / 1000 in ms, load1
of the invoke scenario; `cont8` had 8 busy loops of our own on the same 8 CPUs, a controlled contention):

| pair | load before / after | before w0 / w1000 | after w0 / w1000 | after - before (w0 / w1000) |
|---|---|---|---|---|
| 5 | 3-2 / 2-2 | 1.80 / 1.80 | 1.70 / 1.70 | -0.10 / -0.10 |
| 6 | 2-3 / 4-6 | 1.73 / 1.78 | 2.20 / 2.03 | +0.47 / +0.25 |
| 7 | 7-10 / 12-14 | 1.99 / 2.94 | 2.20 / 2.14 | +0.21 / -0.80 |
| 8 | 22-24 / 18-16 | 1.93 / 1.85 | 1.71 / 1.71 | -0.22 / -0.14 |
| 9 | 14-14 / 16-17 | 1.78 / 1.78 | 2.18 / 1.79 | +0.40 / +0.01 |
| 10 | 14-15 / 26-33 | 1.77 / 1.78 | 4.18 / 4.59 | +2.41 / +2.81 (after at a much higher load) |
| 11 | 3-4 / 4-4 | 1.71 / 1.72 | 1.69 / 1.70 | -0.02 / -0.02 |
| 12 | 5-5 / 4-4 | 1.70 / 1.73 | 1.70 / 1.70 | 0.00 / -0.03 |
| 13 (fix round 1) | 81-84 / 82-68 | 4.73 / 5.00 | 7.33 / 7.48 | +2.60 / +2.48 |
| 14 (fix round 1) | 51-43 / 39-38 | 4.99 / 4.10 | 5.15 / 3.46 | +0.16 / -0.64 |
| 15 (fix round 1) | 21-20 / 20-19 | 2.15 / 1.90 | 1.79 / 1.91 | -0.36 / +0.01 |
| 16 (fix round 1) | 20-22 / 25-42 | 2.71 / 2.80 | 5.05 / 5.31 | +2.34 / +2.51 (after at a higher load) |
| cont8 (fix round 1) | 25-36 / 45-39 | 3.47 / 3.53 | 3.99 / 3.38 | +0.52 / -0.15 |

  Read honestly: on a quiet host (pairs 5, 11, 12) 12b is equal or 0.1 ms faster. Under load the pairs scatter both ways: at
  waitMs=0 12b is slower in 8 of 13 pairs (median +0.16 ms over the 11 pairs at comparable load, +2.6 ms in pair 13 at load
  82), at waitMs=1000 the median is -0.03 ms. The base fails too at the loads where 12b first failed (pairs 13 and 14 at load
  38 to 84: both fail; before16 fails at load 20 to 22). What 12b adds on the one-client path was measured directly: (a) the
  "anyone else waiting?" check yields once to the event loop, one extra loop iteration per invoke (the contended cProfile:
  `_run_once` 23,121 calls against 19,821 for 3,300 invokes, 7.0 against 6.0 per invoke), about 25 us on an idle desktop core
  (`wait_synced(inline=True)` 72.6 us against a synchronous barrier's 47.2 us on tmpfs); (b) under contention it does not grow:
  in the contended py-spy profile `Store._alone` is on the stack in 108 of 19,770 server samples (0.55%), and the admission
  and the execution of one operation share one `fdatasync` (3,301 for 3,300 invokes) and one inline sync (6,601 `_sync_now`
  calls, half of which return at once). So the cost is real but about 25 us, against the ~10 to 20 us saved by dropping the
  two `PRAGMA synchronous` switches per invoke; the larger under-load differences are within the run-to-run scatter of this
  host (the same code differs by up to 0.5 ms between consecutive runs at load 14 to 20). Profiles:
  `bench/results/2026-11-15-bmh-worker-12b-profile-contended/{before,after}/` (cProfile and py-spy, 8 busy loops on the
  server's CPUs). The overhead above the fdatasync floor on a quiet host is 0.39 to 0.41 ms (12a: 0.5).
* B1 stays what Task 12a called it: met on a quiet fast machine, not a property that holds on a loaded shared host. Group commit
  cannot change the one-client case (one intent, one `fdatasync`); it changes everything with more than one intent in flight.

### Concurrency: group commit (AMD, `concurrency` scenario, `waitMs=1000`, closed loop)

Operations per second and p50, quiet host (runs 11 and 12, load 3 to 5; runs 8 and 9 at load 14 to 24 agree within 10%):

| case | before (base) | after (12b) | change |
|---|---|---|---|
| dispatch, 1 client | 553 to 556/s, p50 1.7 to 1.8 ms | 541 to 576/s, p50 1.7 to 1.8 ms | unchanged |
| dispatch, 10 clients on 10 devices (spread/10) | 579 to 623/s, p50 15.7 to 15.9 ms | **2,203 to 2,235/s, p50 3.6 ms** | 3.6x |
| dispatch, 100 clients on 100 devices (spread/100) | 568 to 591/s, p50 162 to 163 ms | **6,226 to 6,450/s, p50 15.2 to 15.5 ms** | 10.7x |
| dispatch, 10 / 100 clients on one device | 576 to 584 / 564 to 568/s | 576 to 594 / 557 to 574/s | unchanged (serial by design) |
| process, 100 clients spread | 6,254 to 6,562/s | 6,217 to 7,032/s | unchanged |

Durable throughput across devices now reaches the non-durable (process-mode) ceiling of the single CPython event loop (about
6,300/s): the fsync is no longer the bottleneck. Operations queued on one device still need one sync each (the next one is
dispatched only after the previous completes); syncing those inline keeps their rate where it was. The first 12b policy offloaded
those syncs to the thread whenever more than one request was in flight; under load 12 to 41 that made the serial chain slower (the
100-client same-device warm-up overran its 2 s wait in `after7` and in the first full run), which is why commit `03140b0` replaced
it with the "anyone else waiting?" check. The warm-up itself now waits for queued work to finish (a harness fix).

### Gateway forwarding (`gateway_forward` scenario, new; quiet host, runs 3 and 4)

| gateway journal | clients | before (base) | after (12b) |
|---|---|---|---|
| dispatch (pending-forward barrier) | 1 | 420 to 457/s, p50 2.02 to 2.19 ms | 351 to 433/s, p50 2.10 to 2.23 ms |
| dispatch | 10 | 263 to 400/s, p50 22 to 23 ms | **1,046 to 1,145/s, p50 8.1 to 8.4 ms** |
| dispatch | 100 | 267 to 278/s, p50 345 to 388 ms | **917 to 1,248/s, p50 45 to 112 ms** |
| process (no barrier) | 1 / 10 / 100 | 1,660 to 1,773 / 1,969 to 2,322 / 2,161 to 2,303/s | 1,661 to 1,770 / 2,173 to 2,462 / 1,854 to 2,607/s |

One forward on its own still waits for one fsync (2.1 ms against 0.55 ms without a barrier): that is the cost of the barrier, and it
is kept (below). Concurrent forwards now share it: 3.3 to 4.5x the throughput at 10 and 100 clients, half of the no-barrier
ceiling on this single-loop test. The `gateway` scenario's per-invoke overhead (dispatch journal, one client) is 1.89 / 1.92 ms (waitMs 0 / 1000; 12a run 4: 2.15 / 2.80 ms). In the two full runs the 100-client forwarding cell, which runs in the harness process right after the 1,000-upstream `gateway` scenario, showed one stall of about 1.2 s (p99 1,204 and 1,231 ms, 520 and 660/s); run alone it never did (max 148 to 201 ms). That is most likely a garbage collection of the harness process over the previous scenario's heap (the harness does not freeze its own heap); it is not a budget and was not pursued further.

### TypeScript journal (`ts_vs_py`, `axis-1.pulse`, `waitMs=1000`; quiet host, runs 3 and 4)

| server | before (base) | after (12b) |
|---|---|---|
| TypeScript, durable | p50 8.10 / 8.38 ms, 92 to 110/s | **p50 4.17 / 4.67 ms, 207 to 225/s** |
| Python, durable | p50 5.05 / 5.22 ms | p50 4.84 / 4.59 ms |
| TypeScript / Python, no store | 1.30 / 1.30 to 1.40 ms | 1.28 to 1.29 / 1.27 to 1.34 ms |

One fsync per invoke instead of three: the TypeScript durable p50 halves and is now at (or below) the Python server's.

### Hot paths

* Statements per durable invoke (traced on the server's connection, `tests/test_hot_paths.py`): 11 with 2 commits before
  (`PRAGMA synchronous=FULL`, BEGIN, INSERT operation, 2x INSERT history, COMMIT, `PRAGMA synchronous=NORMAL`, BEGIN, UPDATE,
  INSERT history, COMMIT) -> **8 with 2 commits**, no PRAGMA.
* The client builds no `TypeAdapter` per call (57 us per call in the 12a profile). Together with the statement and toggle
  savings, the quiet-host durable p50 is 0.05 to 0.1 ms lower (1.69 to 1.71 against 1.70 to 1.80 ms) and process mode
  0.18 against 0.19 ms; memory mode 0.14 against 0.15 ms. These are small, as Task 12a predicted.
* `gc.freeze()` at serve: the one-time generation-2 collection over the start-up heap fell from 29 to 90 ms (collecting 29,053
  objects) to 7 to 40 ms collecting 62 to 96 objects (tail experiment GC logs below).

### Tail stalls (item 5): cause established

`bench/scripts/tail_experiment.py` now attributes every invoke slower than 10 ms to what overlapped it in time: an `fdatasync`
over 5 ms in the server, a server event-loop stall, a client event-loop stall (`bench/stalls.py`), or nothing. Two runs of 3
rounds x 3 variants x 8,000 sequential durable invokes (`2026-11-14-bmh-worker-12b-tail-run1`, `2026-11-15-...-tail-run2`):

* **The 60 to 360 ms stalls are single `fdatasync` calls of the same length.** Per round, the slowest invoke against the
  server's slowest `fdatasync` (and the event-loop stall it caused, the sync running inline on the loop), as measured:

  | run / round | as shipped | checkpointer off | no gc.freeze |
  |---|---|---|---|
  | run 1, round 1 | 17.8 / 158.9 (loop 159.3) ms | 95.9 / 98.5 (99.2) | 100.8 / 99.8 (100.3) |
  | run 1, round 2 | 62.4 / 61.3 (62.0) | 62.4 / 134.9 (134.8) | 99.6 / 98.7 (97.4) |
  | run 1, round 3 | 10.7 / none over 5 ms | 107.2 / 106.1 (105.0) | 55.4 / 29.8 (50.0) |
  | run 2, round 1 | 62.4 / 191.6 (192.6) | 120.7 / 119.5 (118.6) | 359.1 / 321.1 (356.9) |
  | run 2, round 2 | 26.1 / 19.0 (22.7) | 122.5 / 260.4 (261.7) | 23.6 / 21.8 (21.5) |
  | run 2, round 3 | 66.0 / 170.5 (171.2) | 120.9 / 119.6 (118.6) | 172.8 / 171.0 (170.9) |

  In 12 of the 18 rounds the slowest invoke is within about 5 ms of the slowest `fdatasync` or of the loop stall it caused;
  one round had no sync over 5 ms. In the other five (run 1 round 1 and run 2 rounds 1 and 3 as shipped: 17.8, 62.4 and 66.0
  ms invokes against 158.9, 191.6 and 170.5 ms syncs; and the two checkpointer-off rounds with 134.9 and 260.4 ms syncs) the
  slowest sync did not fall on a measured invoke (the 200 warm-up invokes, or the store's own barriers at start-up), and the
  loop stall it caused matched it all the same. Of the run-2 invokes over 10 ms, 175 of 234, 25 of 26 and 30 of 33 (as shipped), 8 of 8, 37 of 48 and 7 of 7
  (checkpointer off), 12 of 12, 68 of 77 and 9 of 10 (no gc.freeze) overlapped an `fdatasync` over 5 ms. The client's own loop
  was never the cause (worst client stall 17.8 ms, 11 samples in the most loaded round). The raw fsync probe of the bench runs
  shows the same disk tail (`fdatasync` max 35 to 239 ms). It is the shared NVMe (or its filesystem journal under other
  tenants' writes), not the checkpointer (the variant with it off has the same maxima) and not the garbage collector (it is
  frozen now; the remaining gen-2 collections are 7 to 40 ms over fewer than 100 objects and their timing does not match the
  stalls).
* Not fixable in BHMS: a durable invoke is bound to its own fsync. On the **thread path** (more than one intent waiting) a slow
  sync no longer holds other intents: the loop keeps serving and later intents join the next sync. On the **inline path** (a
  lone intent, and every synchronous barrier) the sync runs on the event loop, which reads nothing while it lasts: a request
  that arrives meanwhile, `stop` included, waits for it (the loop stalls above are exactly that).

**Stop latency on a durable server (Ruling R48).** Because of the inline path, the time from a `stop` arriving to its stop
procedure being dispatched is bounded by one `fdatasync` in flight: typically about 1.3 ms on this host; the largest
inline-sync loop stall measured is 261.7 ms (run 2, round 2, checkpointer-off variant), and 356.9 ms in the variant without
the heap freeze (run 2, round 1). The design is kept (the inline sync is
what keeps a lone client's latency at the 12a level); a `stop` reader that does not share the journal's event loop is
recorded as a v0.2 idea in the spec CHANGELOG.

### Workstation (quick sizes; i7-10700KF, fsync p50 2.85 to 3.25 ms, load 4 to 7)

Three interleaved quick runs each (`2026-11-14-workstation-12b-ws-*`): B1 fails both before (0 of 3 runs under the fdatasync floor)
and after (0 of 3) by 0.1 to 1 ms at p50 (100 samples per cell make these noisy: one after run read 6.2 ms at waitMs=0 against 4.3
and 4.2 in the other two); a 300-sample interleaved check gave 3.95 to 4.16 ms after against 4.56 to 4.67 ms before. B2 passes in
2 of 3 runs on both sides (process 0.51 to 0.69 ms on this quieter desk host; 12a had 1.4 ms at load 11 to 15). Concurrency
spread/100: 189 to 238/s before, 1,316 to 1,935/s after; gateway forwarding dispatch/100: 202 to 206/s before, 748/s after.

### The gateway barrier decision (item 3)

Kept, with group commit. Reason (now in 07 §7.6): the pending-forward record is the gateway's only evidence that a forward left.
If it were only written, a power loss after the send would lose it: the gateway could not report the operation `unknown` or inhibit
its resources, and the client's same-key retry would send it again, which the upstream deduplicates only while it keeps its own
journal (BHMS-OPS-030, BHMS-OPS-081); an upstream whose epoch changed (a reset or non-durable store) would act twice. The
evidence that the barrier is not free is above (one fsync per lone forward); the evidence that it no longer serialises the gateway
is the 3.3 to 4.5x at 10 and 100 clients. Tests: `test_nothing_is_forwarded_before_the_pending_row_is_durable`,
`test_a_pending_row_that_cannot_be_made_durable_sends_nothing` (tests/test_gateway_routing.py). Task 5's "no barrier needed" note is
withdrawn in the CHANGELOG.

### The full run after the changes (`2026-11-15-bmh-worker-12b-after-full3`, load 4 to 11)

Every scenario of `bench/run.py --full` (simavr from the AVR container of the same session); all budgets PASS in this run.
`python bench/tables.py bench/results/2026-11-15-bmh-worker-12b-after-full3` prints every table; the cells that changed:

| cell | 12a run 4 | 12b after-full3 |
|---|---|---|
| invoke unix/dispatch waitMs 0 / 1000, p50 | 1.80 / 1.81 ms | 1.69 / 1.78 ms |
| invoke unix/process waitMs 0, p50 / memory p50 | 0.21 / 0.17 ms | 0.18 / 0.15 ms |
| concurrency dispatch/spread/100 | 576/s, p50 164 ms | 5,399/s, p50 17.6 ms |
| concurrency dispatch/same-device/100 | 546/s | 529/s |
| gateway overhead, dispatch journal, waitMs 0 / 1000 | +2.15 / +2.80 ms | +1.89 / +1.92 ms |
| TypeScript / Python durable server (`ts_vs_py`) | 6.08 / 4.71 ms | 3.92 / 3.14 ms |
| MCP bridge / native | 3.23 / 2.13 ms | 3.01 / 1.71 ms |
| compact native invoke p50; simavr invoke p50 | 0.041; 7.17 ms | 0.043; 7.16 ms |
| crash recovery, 1,000 unknown operations, restart to first response (all reported unknown) | 0.756 s | 0.824 s (baseline without operations 0.748 s) |

### Remaining misses

* **B1 under load** (above): the remaining non-disk time on a quiet host is 0.39 to 0.41 ms (Python, server and client, see the
  12a profile below); under CPU contention it grows past the 1 ms allowance. A native transport (uvloop, proposal 7) is the only
  lever left on the one-client path and was not done (out of scope until 1 to 4 were done; it would also be a new optional
  dependency).
* Same-device durable throughput is about 560/s: one sync per operation, by design (an intent of a queued operation becomes
  durable only when it is dispatched, so that it recovers `rejected`, not `unknown`; Task 12a proposal 1's caveat, not changed).


# Task 12a record (before the changes)

## Task 12a verdict (before)

BHMS meets its throughput and scale budgets and misses its latency budgets as a *reliable* property. The durable path is bound by
the disk's `fsync`, the non-durable path by CPython; both scale to the hardware's limit rather than collapsing. Concretely:

* **B1 (durable invoke p50 <= floor + 1 ms, p99 <= 5x that): FAIL as a standing budget.** Over four full runs on the AMD machine it
  passes in 2 of 4 (runs 2 and 4, load 12 to 16) and fails in 2 of 4 (run 1, load 15 to 18, by 0.16 ms; run 3, load 25, both waits),
  under *either* floor (the host `fdatasync` p50, 1.30 ms, or the measured SQLite WAL `synchronous=FULL` commit p50, 1.39 to 1.50 ms).
  Durable invoke is the floor plus about 0.5 ms when the host is quiet (1.8 ms), so the 1.0 ms allowance leaves 0.5 ms of margin
  that a busy shared host removes. It passes only on the quietest runs (run 1, at load 15 to 18, already missed). On the developer workstation (fsync 3.0 ms,
  slower loaded CPU) it fails by 1 ms.
* **B2 (non-durable p50 <= 1 ms): PASS on the AMD machine in 4 of 4 runs** (0.21 to 0.45 ms; no-store 0.17 to 0.32 ms) and **FAIL on
  the workstation** (1.4 to 1.7 ms), where the same Python runs about 6x slower per call.
* **One fsync per intent caps durable throughput at about 550 operations per second**, however many clients there are (100 clients:
  546 to 576 ops/s, p50 164 to 182 ms in a closed loop). Non-durable throughput with 100 clients is 3,600 to 6,100 ops/s. This is the
  one clear scalability gap; group commit (Ruling R12) is the fix and is the first item for 12b.
* **Open-loop tail at a given load** (Poisson arrivals, latency from the scheduled arrival): durable invokes at 50% of capacity
  (about 280/s) have p50 4 to 10 ms but **p99 211 to 313 ms**; at 90% p99 40 to 229 ms. The tail is dominated by rare 90 to 300 ms
  stalls of the durable path that every arrival during the stall queues behind (see Tail latency).
* The gateway lists 1,000 upstreams / 10,000 devices correctly (asserted: each device once, in code-point order), pages them in under
  27 ms per page (p99) over unix and HTTP, and starts in 3.2 to 3.7 s. Event fan-in through 1,000 upstream streams runs at 13 to 17
  thousand events per second. These are single-event-loop CPU tests, not connection tests.
* A compact invoke is 35 to 37 bytes on the wire (reply 31 to 34): well inside 64 bytes. Over simavr at 115200 baud the round trip is
  7.2 ms, of which 6.2 ms is the arithmetic wire time.

## Budgets: pass or fail with the measured number

Runs on the AMD machine, `bench/results/2026-11-13-bmh-worker-amd-run1` .. `run4`. Run 4 (full sizes, load 11 to 12 during the invoke
scenario) is the run whose tables are published below and whose **raw per-sample data is committed** (`run4/samples/*.json.gz`, one file
per latency cell, arrival order). Runs 1 to 3 predate the sample dump and are kept as they were. Host `fsync` on that filesystem
(run 4): **`fdatasync` p50 1.30 ms, p99 1.53 ms; SQLite WAL FULL commit p50 1.39 ms, p99 1.50 ms**.

| id | budget | verdict | evidence |
|---|---|---|---|
| B1 | durable invoke p50 <= floor + 1 ms, p99 <= 5x that (`dispatch`, unix, one client, waitMs 0 and 1000), under the fdatasync floor and under the SQLite FULL commit floor | **FAIL under both floors: 2 of 4 runs pass** (pass only on the quietest runs) | table below; run 4 alone: p50 1.80 / 1.81 ms vs limits 2.30 (fdatasync) and 2.39 (SQLite FULL), p99 3.13 / 4.13 vs 11.5 / 11.9: PASS |
| B2 | non-durable "process" mode p50 <= 1 ms | **PASS on AMD (4 of 4 runs); FAIL on the workstation** | AMD run 4: process 0.21 (waitMs=0), 0.24 (waitMs=1000); memory (no store) 0.17 / 0.19. Workstation (quick sizes): process 1.41 / 1.69, memory 1.43 / 1.37 |
| B3 | gateway with 1,000 upstreams lists correctly | **PASS** (run 4) | the paged catalog equals the expected 10,000 ids `u<i>/d<j>` exactly, in code-point order: listed 10000, unique True, ordered True, equals expected True; start 3.66 s. Asserted in `budgets.py` from `scenarios/gateway.py`'s `listing` |
| B4 | `devices/list` over 10,000 devices pages in <= 50 ms | **PASS** | run 4 p99 per page: gateway_scale unix limit 100 0.9 ms, 500 11.6 ms; gateway_http unix 100 1.2 ms, 500 10.5 ms; HTTP 100 2.0 ms (max 19.9), HTTP 500 26.1 ms. Workstation worst: HTTP 500 p99 34.2 ms |
| B5 | compact typical invoke frame <= 64 bytes | **PASS** | request 35 to 37 bytes, reply 31 to 34 bytes (largest 37) |

### B1 across runs (recomputed from the raw JSON by `bench/aggregate.py`)

| run | load1 (invoke scenario) | fdatasync p50 | SQLite FULL p50 | dispatch w0 p50 / p99 | dispatch w1000 p50 / p99 | B1 vs fdatasync | B1 vs SQLite FULL | B2 (process) |
|---|---|---:|---:|---|---|---|---|---|
| run1 | 15 to 18 | 1.31 | 1.40 | 2.12 / 5.03 | 2.47 / 5.72 | FAIL (w1000 p50) | FAIL (w1000 p50) | PASS |
| run2 | 16 to 14 | 1.30 | 1.50 | 1.79 / 3.00 | 1.80 / 2.95 | PASS | PASS | PASS |
| run3 | 26 to 26 | 1.56 | 1.50 | 3.37 / 10.01 | 2.70 / 9.06 | FAIL (w0 p50, w1000 p50) | FAIL (w0 p50, w1000 p50) | PASS |
| run4 | 12 to 12 | 1.30 | 1.39 | 1.80 / 3.13 | 1.81 / 4.13 | PASS | PASS | PASS |

* B1 under the fdatasync floor: **FAIL**, 2 of 4 runs pass (run2, run4; load1 16-14, 12-12).
* B1 under the SQLite FULL commit floor: **FAIL**, 2 of 4 runs pass (run2, run4; load1 16-14, 12-12).
* B2 (process mode, p50 <= 1 ms): 4 of 4 runs pass.

A run passes under a floor when all four cells (waitMs 0 and 1000, p50 and p99) pass. Workstation (quick, fsync 2.99 ms, load 12): FAIL, p50
5.05 / 5.02 ms vs 3.99 ms (2.0 ms above the fsync); p99 passes.

How B1 and B2 are judged (`bench/budgets.py`): a fresh server process per cell, one client, an action that returns at once, 1,000 samples
after warm-up, against the floor measured in the same run on the same filesystem; B2 on the same cells with `durability="process"` and with
`store=None`. B1 and B2 are CPU-bound budgets stated as if they were disk-bound: CPython needs about 0.5 ms on a fast core, so the
margin is 0.5 ms, and a single contended fsync or a descheduled event loop on a shared host consumes it. On a slower or busier core the
Python overhead alone exceeds 1.0 ms (see the proposals). Every verdict is in `budgets.json` of each run directory.

### Variance across the four AMD runs

The machine is shared (load average 11 to 27 on 32 cores). Client, server and harness all run on the same 8 pinned cores
(`taskset`); the NVMe, the ext4 journal and memory bandwidth are shared with other tenants. Same code, same sizes:

| quantity | run 1 | run 2 | run 3 | run 4 |
|---|---|---|---|---|
| load1 around the invoke scenario | 15 to 18 | 16 to 14 | 26 | 12 |
| host fdatasync p50 / p99 (ms) | 1.31 / 2.13 | 1.30 / 1.49 | 1.56 / 5.64 | 1.30 / 1.53 |
| dispatch waitMs=0 p50 / p99 (ms) | 2.12 / 5.03 | 1.79 / 3.00 | 3.37 / 10.01 | 1.80 / 3.13 |
| dispatch waitMs=1000 p50 / p99 (ms) | 2.47 / 5.72 | 1.80 / 2.95 | 2.70 / 9.06 | 1.81 / 4.13 |
| process waitMs=0 p50 (ms) | 0.33 | 0.21 | 0.38 | 0.21 |
| max latency, dispatch w0 / w1000 (ms) | 213 / 155 | 126 / 17 | 224 / 165 | 18 / 88 |

Run 1 also includes one harness defect: its `mcp_compare` scenario failed (`CallToolResult` has `is_error` in mcp 2.x, not
`isError`); the harness was fixed before runs 2 and 3. The run-1 directory is kept unedited, as evidence of the variance.

## Environment

AMD machine (`ssh bmh-worker`): AMD RYZEN AI MAX+ PRO 395 (HP Z2 Mini G1a), 32 logical CPUs, 91.8 GB RAM, Ubuntu 26.10, kernel
7.3.0-9, Python 3.12.16, Node v20.20.1 (user-space tarball under `~/hms-lab/node`, 28 MB), `mcp` 2.3.0, websockets 17.4, aiohttp
3.14.5, pydantic 2.14.3. State directory on `/dev/nvme0n1p6` ext4 `rw,relatime` (not tmpfs: the fsync cost is the point). Each
run: `nice -n 10 taskset -c <8 least-busy CPUs>`; the CPU list is in each `environment.json`. Load average is recorded before and
after every measurement (`load1` column); the whole machine was at load 11 to 27 throughout.

Workstation (comparison, no installs): Intel Core i7-10700KF, 16 logical CPUs, Ubuntu 24.04, kernel 7.0.0-42, Python 3.12.3,
Node v20.20.1 (nvm), ext4 `noatime` on NVMe, load 11 to 15 (the desk machine was busy). `--quick` sizes only (100 samples per
latency cell), so percentiles beyond p95 are coarse there.

Sizes: `--full` is 1,000 sequential samples per invoke cell after 200 warm-up, 2,000 to 5,000 operations per concurrency cell,
200 events per fan-out cell, 1,000 upstreams for the gateway. Client and server are separate processes everywhere except the
`gateway*` scenarios, which follow Task 5's benchmark and run the gateway, its in-process light upstreams and the client on one
event loop (so they measure the gateway's CPU cost, not 1,000 real peers: single-event-loop CPU tests, not connection tests). The gateway scenarios imported unchanged from `sdk/python/benchmarks/gateway_scale.py` report summaries only (no per-sample data); the same paging and invokes are re-measured with raw samples in `gateway_http`. The `RSS +` figures of that scenario are peak-RSS deltas and read 0.0 when an earlier scenario in the same process already peaked higher (run 4); runs 1 to 3 show +221 MB.

Closed-loop concurrency (the `concurrency` scenario): each client sends its next invoke only after the previous answer, so the
latencies there are service time plus queueing behind the other clients in a closed loop, not the tail an open arrival process
produces; the `openloop` scenario below measures that.

Percentiles are nearest-rank (`bhms.cli.bench.summarize`, the same code as `bhms bench`). Failures are counted, never dropped:
every cell below had 0 failures.

## Scenarios

`bench/scenarios/`: `fsync`, `transports`, `invoke`, `concurrency`, `openloop`, `gateway` (Task 5's `gateway_scale.py` imported as is),
`gateway_http`, `subscription`, `recovery`, `compact`, `mcp_compare`, `ts_vs_py`. `bench/README.md` describes each. Run:
`python bench/run.py --quick` or `--full`.

## Results (run 4, samples committed)

Columns are samples, p50, p95, p99, max in milliseconds, operations per second, and the load average at the start and end of the
measurement.

### Host fsync (state directory filesystem)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| fdatasync 600B | 3000 | 1.30 | 1.41 | 1.53 | 58.55 | 732 | 12.4->12.3 |
| fsync 600B | 3000 | 1.30 | 1.41 | 1.49 | 9.02 | 750 | 12.4->12.3 |
| fdatasync 4096B | 3000 | 1.31 | 1.41 | 1.50 | 27.68 | 736 | 12.4->12.3 |
| fsync 4096B | 3000 | 1.30 | 1.41 | 1.49 | 8.92 | 744 | 12.4->12.3 |

SQLite WAL commit (600 B row): NORMAL p50 0.0039 ms / p99 0.0123; FULL p50 1.3866 ms / p99 1.5024.

### Transports, ping only

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix sequential | 5000 | 0.03 | 0.03 | 0.06 | 0.61 | 34612 | 12.3->12.3 |
| tcp sequential | 5000 | 0.03 | 0.04 | 0.06 | 0.17 | 31437 | 12.3->12.2 |
| websocket sequential | 5000 | 0.04 | 0.06 | 0.09 | 0.25 | 22240 | 12.2->12.2 |
| stdio sequential | 5000 | 0.03 | 0.04 | 0.08 | 0.26 | 29942 | 12.2->12.2 |

Pipelined (256 in flight): unix 120842/s, tcp 131139/s, websocket 75635/s, stdio 162708/s

### `actions/invoke`, one client, sequential

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix/full/waitMs=0 | 1000 | 3.20 | 3.83 | 4.28 | 20.41 | 303 | 12.2->11.9 |
| unix/full/waitMs=1000 | 1000 | 3.35 | 4.00 | 5.32 | 89.91 | 281 | 11.9->11.9 |
| unix/dispatch/waitMs=0 | 1000 | 1.80 | 2.13 | 3.13 | 17.60 | 534 | 11.9->11.9 |
| unix/dispatch/waitMs=1000 | 1000 | 1.81 | 2.28 | 4.13 | 88.27 | 500 | 11.9->12.1 |
| unix/process/waitMs=0 | 1000 | 0.21 | 0.33 | 0.45 | 16.63 | 3992 | 12.1->12.1 |
| unix/process/waitMs=1000 | 1000 | 0.24 | 0.40 | 0.53 | 26.55 | 3433 | 12.1->12.1 |
| unix/memory/waitMs=0 | 1000 | 0.17 | 0.26 | 0.41 | 23.93 | 4866 | 12.1->12.1 |
| unix/memory/waitMs=1000 | 1000 | 0.19 | 0.31 | 0.50 | 22.30 | 4266 | 12.1->12.1 |
| ws/dispatch/waitMs=0 | 1000 | 1.84 | 2.18 | 2.88 | 21.60 | 525 | 12.1->12.0 |
| ws/dispatch/waitMs=1000 | 1000 | 1.88 | 2.18 | 2.86 | 136.78 | 485 | 12.0->12.0 |
| ws/memory/waitMs=0 | 1000 | 0.22 | 0.37 | 0.51 | 22.95 | 3760 | 12.0->12.0 |
| ws/memory/waitMs=1000 | 1000 | 0.23 | 0.41 | 0.60 | 23.41 | 3417 | 12.0->12.0 |
| stdio/dispatch/waitMs=0 | 1000 | 1.79 | 2.03 | 3.08 | 120.84 | 518 | 11.9->11.9 |
| stdio/dispatch/waitMs=1000 | 1000 | 1.78 | 2.15 | 3.00 | 20.87 | 537 | 11.9->11.9 |
| stdio/memory/waitMs=0 | 1000 | 0.17 | 0.26 | 0.37 | 17.68 | 5094 | 11.6->11.6 |
| stdio/memory/waitMs=1000 | 1000 | 0.18 | 0.29 | 0.46 | 15.46 | 4625 | 11.6->11.6 |

### Concurrent clients (`waitMs=1000`, unix)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| dispatch/same-device/1 | 2000 | 1.81 | 2.14 | 2.93 | 74.90 | 517 | 11.6->11.6 |
| dispatch/same-device/10 | 2000 | 17.27 | 19.22 | 40.66 | 116.45 | 553 | 11.6->11.6 |
| dispatch/same-device/100 | 2000 | 182.09 | 192.11 | 196.29 | 196.89 | 546 | 11.4->11.4 |
| dispatch/spread/10 | 2000 | 16.15 | 17.89 | 24.49 | 32.51 | 606 | 11.4->11.7 |
| dispatch/spread/100 | 2000 | 163.77 | 243.02 | 260.44 | 263.12 | 576 | 11.7->11.5 |
| process/same-device/1 | 5000 | 0.23 | 0.36 | 0.51 | 18.79 | 3871 | 11.5->11.5 |
| process/same-device/10 | 5000 | 1.98 | 2.19 | 2.81 | 17.70 | 4933 | 11.5->11.1 |
| process/same-device/100 | 5000 | 27.06 | 31.21 | 35.19 | 39.81 | 3636 | 11.1->11.1 |
| process/spread/10 | 5000 | 1.48 | 1.85 | 2.23 | 19.08 | 6441 | 11.1->11.1 |
| process/spread/100 | 5000 | 14.97 | 19.79 | 53.91 | 54.21 | 6094 | 11.1->11.3 |

### Open-loop latency (Poisson arrivals at a fixed offered rate; latency from the scheduled arrival)

| case | offered/s | achieved/s | n (failed) | p50 ms | p95 ms | p99 ms | max ms | load1 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| dispatch 50% of capacity (capacity 560/s) | 280 | 285 | 4280 (0) | 3.99 | 98.27 | 211.08 | 304.46 | 11.3->10.8 |
| dispatch 90% of capacity (capacity 560/s) | 504 | 509 | 7644 (0) | 7.57 | 27.80 | 40.37 | 97.89 | 10.8->10.7 |
| process 50% of capacity (capacity 6485/s) | 3243 | 1658 | 48850 (0) | 1284.46 | 13016.19 | 14014.26 | 14826.87 | 11.1->14.0 |
| process 90% of capacity (capacity 6485/s) | 5837 | 101 | 13781 (74084) | 66956.85 | 106535.27 | 107167.40 | 107627.92 | 14.0->22.2 |

### Gateway, 1000 upstreams x 10 devices (in-process upstreams)

start 3.66 s, background validation 2.8 s, RSS +0.0 MB; devices 10000.

| paging | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|---:|
| limit_100_ms | 100 | 0.693 | 0.793 | 0.885 | 0.885 |
| limit_500_ms | 20 | 5.507 | 11.607 | 11.607 | 11.607 |

Event fan-in: 5000 events from 1000 upstream streams in 0.323 s = 15483/s; latency under the burst p50 266.992 / p99 311.083 / max 311.733 ms; +0.0 MB.

| invoke via | n | p50 ms | p95 ms | p99 ms | max ms | overhead p50 ms |
|---|---:|---:|---:|---:|---:|---:|
| direct_wait0 | 1000 | 0.189 | 0.253 | 0.353 | 6.103 | - |
| direct_wait1000 | 1000 | 0.214 | 0.317 | 0.425 | 0.981 | - |
| gateway_process_wait0 | 1000 | 0.576 | 0.845 | 1.048 | 1.882 | 0.387 |
| gateway_process_wait1000 | 1000 | 0.655 | 0.962 | 1.339 | 2.334 | 0.441 |
| gateway_dispatch_wait0 | 1000 | 2.339 | 3.076 | 3.865 | 10.449 | 2.15 |
| gateway_dispatch_wait1000 | 1000 | 3.014 | 6.826 | 11.159 | 19.836 | 2.8 |

### Gateway over unix versus Streamable HTTP (10001 devices)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| unix devices_list_limit_100 | 303 | 0.77 | 1.10 | 1.17 | 1.19 | 1194 | 20.3->20.3 |
| unix devices_list_limit_500 | 63 | 4.07 | 7.03 | 10.50 | 10.50 | 236 | 20.3->20.3 |
| unix invoke_waitMs_0 | 500 | 0.47 | 0.56 | 0.70 | 1.07 | 2056 | 20.3->20.3 |
| unix invoke_waitMs_1000 | 500 | 0.57 | 0.69 | 0.92 | 1.30 | 1700 | 20.3->20.3 |
| http devices_list_limit_100 | 303 | 1.00 | 1.53 | 2.02 | 19.93 | 843 | 20.3->19.9 |
| http devices_list_limit_500 | 63 | 5.11 | 9.92 | 26.05 | 26.05 | 163 | 20.3->19.9 |
| http invoke_waitMs_0 | 500 | 0.82 | 1.01 | 1.37 | 1.77 | 1175 | 20.3->19.9 |
| http invoke_waitMs_1000 | 500 | 0.91 | 1.13 | 1.57 | 30.29 | 999 | 20.3->19.9 |

### Subscription fan-out (1 event stream to N listeners)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| listeners=1 delivery | 200 | 2.17 | 2.50 | 2.94 | 4.83 | 454 | 19.9->19.9 |
| listeners=1 slowest listener | 200 | 2.17 | 2.50 | 2.94 | 4.83 | 454 | 19.9->19.9 |
| listeners=10 delivery | 2000 | 2.23 | 3.03 | 3.70 | 4.48 | 4171 | 19.9->19.9 |
| listeners=10 slowest listener | 200 | 2.29 | 3.10 | 3.70 | 4.48 | 417 | 19.9->19.9 |
| listeners=50 delivery | 10000 | 4.42 | 6.11 | 7.48 | 96.22 | 9263 | 19.9->19.8 |
| listeners=50 slowest listener | 200 | 4.88 | 6.72 | 7.48 | 96.22 | 185 | 19.9->19.8 |
| listeners=100 delivery | 20000 | 5.09 | 7.85 | 8.86 | 10.22 | 16530 | 19.8->19.8 |
| listeners=100 slowest listener | 200 | 5.74 | 8.83 | 9.48 | 10.22 | 165 | 19.8->19.8 |

Deliveries lost: listeners=1: 0, listeners=10: 0, listeners=50: 0, listeners=100: 0

### Crash recovery (SIGKILL, restart)

| case | journal bytes | to ready s | to first response s | unknown after |
|---|---:|---:|---:|---:|
| devices=1000 unknown=0 | 9136512 | 0.756 | 0.757 | 0 |
| devices=10 unknown=10 | 514816 | 0.233 | 0.235 | 10 |
| devices=100 unknown=100 | 4329936 | 0.257 | 0.258 | 100 |
| devices=1000 unknown=1000 | 48245720 | 0.755 | 0.756 | 1000 |

### BHMS-Compact

| target | op | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---:|---:|---:|---:|---:|
| native | invoke | 3000 | 0.0408 | 0.049 | 0.0631 | 0.2258 |
| native | read | 1500 | 0.041 | 0.049 | 0.0588 | 0.0682 |
| simavr | invoke | 1000 | 7.1654 | 7.226 | 8.2137 | 9.9782 |
| simavr | read | 500 | 7.1917 | 7.2547 | 7.6726 | 9.6887 |

native: invoke request [35, 36, 37] bytes, reply [31, 32, 34], read frames [29, 30, 31, 40, 41, 42, 43], hello 48;

simavr: invoke request [35, 36, 37] bytes, reply [31, 32, 34], read frames [29, 30, 40, 41, 42], hello 48; wire floor 6.163 ms at 115200 baud, p50 over floor 1.002 ms;

(From `run4-compact-rerun`, the compact scenario re-run alone with raw samples; the main run-4 compact numbers are within 10%.)

### MCP bridge versus native client

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| native | 1000 | 2.13 | 3.38 | 5.76 | 102.72 | 392 | 19.2->19.2 |
| mcp_bridge | 1000 | 3.23 | 6.08 | 7.68 | 91.60 | 262 | 19.2->18.7 |

Bridge overhead p50 1.098 ms; tool result text 82 bytes; `tools/list` 1.685 ms.

### TypeScript SDK server versus Python SDK server (`axis-1.pulse`, `waitMs=1000`, unix)

| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |
|---|---:|---:|---:|---:|---:|---:|---|
| python/durable | 1000 | 4.71 | 7.09 | 8.92 | 94.64 | 193 | 18.7->18.1 |
| typescript/durable | 1000 | 6.08 | 7.51 | 9.60 | 90.71 | 159 | 18.1->17.7 |
| python/memory | 1000 | 1.38 | 1.65 | 1.78 | 21.36 | 706 | 17.7->17.2 |
| typescript/memory | 1000 | 1.42 | 1.63 | 1.75 | 2.31 | 711 | 17.2->17.2 |

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

* **Transports are not the cost.** Bare ping round trip is 0.03 ms (unix, tcp, stdio) and 0.04 (websocket) in run 4 (0.05 to 0.11 in run 2); pipelined
  throughput 76 to 163 thousand requests per second. A non-durable invoke (0.17 to 0.24 ms) is several times a ping, and the
  durable invoke is the same across unix, websocket and stdio (1.80, 1.84, 1.79 ms): durability dominates, transport does not.
* **Durability costs one fsync per fsync.** `full` (synchronous=FULL everywhere) 3.2 to 3.35 ms; `dispatch` (one barrier on the
  intent) 1.8 ms; `process` 0.21 ms; `memory` 0.17 ms. That is `fsyncs x 1.3 ms + 0.2 to 0.5 ms`. `dispatch` is already
  the minimum for "intent durable before dispatch" without batching.
* **Concurrency.** Durable throughput is flat at 517 to 606 ops/s from 1 client to 100 (same device or spread over 100
  devices): the single journal serialises one fsync per intent, so latency grows linearly with clients (p50 1.8 ms at 1, 17 ms at
  10, 164 to 182 ms at 100). Non-durable throughput scales until CPython's single event loop saturates: 3.6 to 4.9 thousand ops/s
  on one device, 6.1 to 6.4 thousand ops/s spread over 100 devices; p50 at 100 clients is 15 to 27 ms.
* **Gateway.** Over a process-mode journal the gateway adds 0.39 ms (waitMs=0) and 0.44 ms (waitMs=1000) to a direct
  invoke (0.19 to 0.21 ms). With the default `dispatch` journal it adds **2.15 / 2.80 ms**: the gateway writes a
  pending-forward row with a barrier commit before sending (`gateway/journal.py`, `pending_put`), i.e. one fsync per forwarded
  invoke. (Task 5's report says the gateway needs no barrier; the code has one. In front of a durable device server this is two
  fsyncs per invoke end to end; that combination was not measured, see below.) Streamable HTTP adds 0.35 ms per invoke and
  0.2 ms (limit 100) to 1.0 ms (limit 500) per `devices/list` page over the unix socket (p50).
* **Subscription fan-out** is linear and cheap: delivery latency (invoke to listener parse) p50 2.2 ms with 1 listener, 2.2 ms
  with 10, 4.4 ms with 50 and 5.1 ms with 100 (p99 8.9 ms): about 0.03 ms per listener; no delivery lost in any cell.
* **Crash recovery** is not the slow part of a restart. SIGKILL with 1,000 running operations on 1,000 devices, restart to first
  response: 0.756 s against 0.757 s with no operations (run 2: 0.76 vs 0.73), so settling 1,000 operations to `unknown` costs at most about 30 ms. The
  constant part is interpreter start, imports and declaring the devices (0.23 s for 10 devices). All N operations were
  reported `unknown` afterwards (nothing lost, nothing invented). The journal holds 48 MB (database plus its
  uncheckpointed WAL) after 1,000 invokes on top of a 9 MB baseline, about 39 KB written per operation; this is the WAL's page-granular
  write amplification, and part of why disk time per invoke is what it is.
* **Compact binding.** Native C endpoint over a pty: 0.041 ms p50 per invoke (0.041 to 0.045 over runs). ATmega328P in
  simavr, 115200 baud: 7.17 ms p50 per invoke and 7.19 ms per read, against a 6.16 ms wire-time floor for the 35-byte request
  and 34-byte reply actually exchanged (10 bits per byte): the device and host add about 1.0 ms; the rest is the serial line.
* **MCP versus native.** The MCP bridge (official `mcp` 2.3 client over stdio to `python -m bhms mcp`) takes 3.23 ms p50
  against 2.13 ms native for the same durable action (+1.10 ms, run 4 at load 19; run 2: 3.08 vs 1.82; run 3: 2.88 vs 1.80): an extra process hop, MCP
  framing both ways, argument validation and rendering. The agent receives 82 bytes of result text; `tools/list` is 1.3 ms.
* **TypeScript versus Python server.** Same conformance-device action (`axis-1.pulse`, which itself holds 1 ms): without a store
  they are equal (1.40 ms both in run 1; 1.38 vs 1.42 in run 4). With the default durable store the TypeScript server is about
  1.3 to 1.5x slower (run 1: 3.92 Python, 5.68 TypeScript; run 3: 4.22 vs 5.72; run 4: 4.71 vs 6.08). Run 2's durable cell ran while the host load climbed from
  14 to 26 (python 6.5, typescript 11.1) and is not comparable. The TypeScript journal fsyncs every operation record
  (`store.ts` `writeOp` -> `append(..., true)`: accepted, dispatching, completed), where the Python server issues one barrier on the
  intent; that is consistent with the gap.

### Open-loop latency at a fixed offered load

`bench/scenarios/openloop.py`: Poisson arrivals at a fixed rate, 20 connections, 100 devices, latency measured from the scheduled arrival
instant (no coordinated omission); the offered rate is a fraction of the closed-loop capacity measured just before. Run 4 (load 11) and
a dispatch/process rerun of that scenario alone (`run4-openloop-rerun`, load 17 to 22, after a harness fix); samples in each `samples/`.

| durability | run | offered / closed-loop capacity | achieved/s | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---|---:|---:|---:|---:|---:|
| dispatch | run 4 | 280/s (50% of 560) | 285 | 3.99 | 98.3 | 211 | 304 |
| dispatch | run 4 | 504/s (90%) | 509 | 7.57 | 27.8 | 40.4 | 97.9 |
| dispatch | rerun | 264/s (50% of 528) | 268 | 9.69 | 227 | 313 | 389 |
| dispatch | rerun | 475/s (90%) | 478 | 11.2 | 152 | 229 | 313 |
| process | rerun | 159/s (10% of 1587) | 163 | 2.81 | 6.6 | 10.6 | 55.1 |
| process | rerun | 317/s (20%) | 323 | 1.91 | 4.1 | 8.4 | 62.4 |

Reading: at half of capacity the durable path's p50 is 4 to 10 ms (against 1.8 ms unloaded) and p99 is 200 to 300 ms: the rare
90 to 300 ms stalls (Tail latency, below) hold arrivals that then queue. That tail is not visible in the closed-loop tables. The run-4
`process` cells (50% and 90% of a 6.5k/s closed-loop capacity) are **invalid**: the single-process Python load generator reached only
1.7k/s and then overflowed (74,084 failed arrivals at the 90% cell); they are kept in `run4/openloop.json` for transparency and
superseded by the rerun at 10% and 20% (the rerun's closed-loop capacity, 1.6k/s, was itself depressed by host load 17 to 22).

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

On the AMD machine process-mode p50 is 0.21 to 0.45 ms (4 runs): a pass. The workstation misses (1.41 / 1.69 ms) because
the same code is about 6x slower per call on a loaded i7: it is a statement about the budget's hardware dependence, not a
different code path. The profile above (client 0.24 ms of Python per call, server about 0.2 ms) is why a 1 ms budget cannot be
promised on every CPU.

### Tail latency: the 100+ ms maxima

The max of durable cells is 90 to 250 ms in most runs (e.g. 126, 168, 213 ms; run 4: 88 ms), against a raw fsync max of 9 to 58 ms.
Raw per-sample data: `bench/results/*/samples/` (one gzip JSON per cell) and `2026-11-13-bmh-worker-profiles/tail_samples/` (each
round and variant below, with the logged GC pauses).
`bench/scripts/tail_experiment.py` (3 rounds x 8,000 invokes x 3 variants) separates the causes. It was run twice: `tail_experiment.txt`
(first run, summaries only) and `tail_experiment_run2.txt` (second run, on a busier host, raw samples committed in `tail_samples/`):

* **A one-time generation-2 garbage collection in the server accounts for the stall near invoke #700**: with a GC callback
  logging pauses, every server run logged one gen-2 collection of 42 to 81 ms that freed about 29,000 objects (and a 20 to 37 ms
  one earlier, at start-up). With `gc.freeze()` after start-up (what `Gateway.serve` already does) that collection falls to 11 to 25 ms and
  the stall at index ~492 disappears from the first-slow-index list in all three rounds.
* The background WAL checkpointer is **not** the cause: with it effectively disabled the 100+ ms maxima remain (110, 203, 121
  ms).
* Rare 100 to 250 ms stalls remain in every variant including `gc.freeze` (max 123, 108 ms; second run 88, 89, 91 ms). They are not GC, not the
  checkpointer, and not seen in a 3,000-sample raw fsync probe (max 35 ms); most likely the shared filesystem or the machine.
  **Cause not established.**

First run: p99 3.5 to 5 ms in all variants and 6 to 12 of 8,000 invokes over 10 ms. Second run (host busier, raw samples committed):
as shipped p99 5.2 to 8.8 ms with 13 to 43 invokes over 10 ms, checkpointer off 5.9 to 8.7 ms with 8 to 35, `gc.freeze` 4.0 to 6.7 ms
with 8 to 20; the index-492 stall is present in all three as-shipped rounds and absent in all three `gc.freeze` rounds. Max stays 62 to 150 ms
in every variant, including `gc.freeze`.

## Proposals for 12b (ordered by expected gain)

1. **Group commit for concurrent intents (Ruling R12).** Evidence: durable throughput is 517 to 606 ops/s at 1, 10 and 100
   clients (one fsync per intent); process mode does 3,600 to 6,400 ops/s with the same code. A commit window shared by every intent
   admitted while the previous fsync runs should lift durable throughput with 100 clients on distinct devices from about 550
   toward the process-mode ceiling (4,000 to 6,000 ops/s: roughly 7x to 11x) and cut p50 at 100 clients from 164 to 182 ms to about
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
5. **Decide the gateway's barrier.** The gateway adds 2.15 to 2.8 ms in `dispatch` mode because of the pending-forward barrier, and the
   Task 5 report says none is needed. If a durable device sits behind it the intent is already durable at the device; dropping
   the gateway barrier (keyed retry already reconciles, per the Task 5 design note) would take 2.15 ms to about 0.4 ms per invoke.
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
* **Raw samples of the imported gateway_scale cells** (the SDK benchmark reports summaries only and `sdk/` was not modified); the equivalent paging and invokes are sampled in `gateway_http`.
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

Result directories (all `bench/results/2026-11-13-...`): `bmh-worker-amd-run1` (load 14 to 18, mcp scenario failed on a harness defect since fixed),
`-run2`, `-run3` (load 25 at the start), `-run4` (published tables; raw samples in `samples/`), `-run4-openloop-rerun` (open-loop cells
after the harness fix), `-run4-compact-rerun` (compact with raw samples), `workstation-quick`, `bmh-worker-profiles` (profiles and the tail
experiments with raw samples). `python bench/aggregate.py <run dirs>` recomputes the B1/B2 aggregate verdict.
