# Local control-path measurements

The first measurements concern original HMS simulation reads over a same-host Linux Unix socket. They include request/result validation and one new connection per request. They do not include physical actuation, MCU scheduling, model inference or Harness orchestration. [Retained samples and environment](../artifacts/verification/local-read-benchmark.json) and [the measurement script](../scripts/benchmark_local.py) are retained. Their source hashes identify the measured snapshot, before the additional client pre-normalization integer check and MCP projection; the table is not a fresh measurement of those additions.

| Path | Samples | Median | 95th percentile | Maximum observed |
|---|---:|---:|---:|---:|
| Warm checked discovery | 20 | 3.00 ms | 3.39 ms | 163.58 ms |
| Warm checked description | 20 | 22.45 ms | 126.09 ms | 127.65 ms |
| Warm checked observation | 20 | 4.21 ms | 4.58 ms | 111.25 ms |
| New CLI process, discovery | 5 | 479.98 ms | 594.82 ms | 594.82 ms |

These are small sequential sample sets using nearest-rank percentiles. The worker continued refreshing three simulated instances; other host load and filesystem latency were uncontrolled. Isolated Harness build/integration work was also underway. This is not an idle-host baseline or a qualified tail-latency estimate. No acceptance limit was selected, and an observed maximum is not a real-time guarantee.

The [earlier run](../artifacts/verification/local-read-benchmark-before-bundle-cache.json) also overlapped the full Python verification suite. Its median checked description read was 257.67 ms. Code inspection identified repeated full validation of immutable type bundles; the implementation now caches only successful pure validation, with at most 32 type-preserving immutable keys of at most 65,536 bytes each. Authorization, freshness, binding and operation checks remain current. The changed host load prevents attributing the entire timing difference to this cache.

Type preservation matters: an exact integer duration and an integral floating-point duration can have identical JCS bytes, while this profile accepts only the former at that field. The validation cache must not merge them. A regression primes the valid integer case, then rejects the floating-point form and a mutated TD. Canonical digest identity remains a separate operation from input-profile validation.

Cold process startup and imports dominate the CLI's simple discovery example. The initial native Harness provider also starts a checked Python bridge for each request; its measurements belong to the integration's separate receipt. A persistent bounded bridge or independently qualified native transport is a future optimization. It must preserve peer authentication, request correlation, bounded queues, cancellation settlement and no automatic mutation retries.

The large observed read tails also rule out treating this host loop as a fast servo controller. A device's time-critical control and protective behavior require the selected local controller profile and measured implementation. Further work needs concurrent-client/load tests, large inventories, telemetry contention, blocked adapters, hub inference load, controller transport and physical response measurements, with explicit acceptance criteria for each supported deployment.
