# Original-worker accounting diagnostic

This is a new measurement scope, not a success-seeking rerun or a timing
qualification. The frozen [proof-build candidate](../../implementation/pat-io-proof-batch/README.md)
remains unchanged, including all 288 project files, the worker entry, supervisor,
complete 30-case test and all source identities. No project code is instrumented.

The retained [primary references](../../../research/host-contract/worker-accounting/README.md)
support parent and waited-child accounting. The harness subclasses the existing
`Popen` class and forwards its constructor, `poll` and `wait` calls. It adds no
poll, wait or signal, uses no numeric PID for authority, and changes no scheduling
or resource settings. The original audit checks the exact executable, image path,
arguments, working directory and environment; a one-launch cap also prevents a
replacement process within this diagnostic.

The observer samples before/after the original test and before launch/at the
first existing poll or wait returning a terminal status. It records the actual
object's PID, monotonic times, inherited directory/input/writer-lease descriptor
identities, raw resource usage and three bounded global pressure files. Final
audit associates these with the original launch input, ledger and writer lease.
This object/descriptor association replaces the earlier proposed PID/start-time
polling: no `/proc/<pid>` counter is read, so PID reuse cannot redirect a sample.

Only documented additive fields receive deltas. Peak RSS remains a raw high-water
value. Block I/O counters are operation counts, not bytes or wait time. Global
pressure is host context. Descendant accounting is limited to descendants waited
for by their parents. No precise wait-cause or per-thread scheduler attribution
is claimed. CPU-to-wall ratios are observations, not deadline guarantees.

Fifteen pure controls use fake process objects to check forwarding, original
timeouts, missing final observations, same-PID/different-object refusal, duplicate
launch refusal, spawn failure, observer failure, unavailable counters, peak/counter
distinctions, regression, read bounds and descriptor errors. Their receipt is
separate from the integration result. Partial diagnostic files survive normal
failure; a killed observer may leave only earlier snapshots. Diagnostic failures
cannot become successful measurements or change the original test's pass status.

The original bounds remain: 60-second worker, 180-second parent, six parent SQLite
opens, 16 MiB file, 256 MiB retained scratch, 8,192 files, 8 MiB log, 15 MiB evidence
vault and five-second held snapshot. No physical provider, MCU, inference, live
service or acquired research code runs. Retain original failures and quiescence
proofs; open no interrupted per-case database. The public runtime is unchanged.
