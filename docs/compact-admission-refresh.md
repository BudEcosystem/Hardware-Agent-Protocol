# Targeted observation refresh before compact admission

The retained [459-test diagnosis](../artifacts/verification/runtime-availability-diagnosis/README.md)
identified `DEVICE_UNAVAILABLE` before admission, with unchanged keys, operations,
claims and compact commands. It did not retain the exact presence row at refusal.
A separate deterministic native/virtual-clock probe reproduces three mechanisms:
presence can expire during a clock checkpoint, during publication commit, or while
another healthy route holds shared authority. These mechanisms do not establish
which one caused that historical run.

The new fresh-invoke path preserves that refusal boundary. An internal
`PresenceAgeExpired` marker is emitted only for an existing matching adapter and
session whose presence expired, after static binding, exact action/read authority,
argument and installed-support checks. Its public error code remains
`DEVICE_UNAVAILABLE`. Missing presence, changed identity and other refusals do not
authorize observation I/O.

`Runtime` first submits normally. Retained replay, conflicting keys and ordinary
admission follow the existing Journal path. Only the typed expiry can enter the
new path. It takes the route lock followed by the Journal mutex, matching worker
order, then submits normally again to account for concurrent replay, revocation
and expiry while waiting. If the same typed expiry remains, it performs one
forced observation refresh and submits the identical canonical bytes once more.
Every Journal transaction is closed before that I/O. There is no retry loop, new
key, changed deadline, lease extension or timestamp renewal of an old sample.

The compact refresh requires an existing ready installation, known boot/context,
fault-free stream and no active Journal transaction. It sends HELLO with
initialization disabled; it does not tick the dispatcher, bind a new installation,
arm or send an operation. A changed endpoint withdraws eligibility. Fresh
observations keep their acquisition/uncertainty provenance. The final normal
admission can still refuse live preconditions, resource contention, freshness,
authority or timing.

This initial path serves primitive `invoke` through Runtime, including its existing
CLI/MCP projections. `prepare`, direct Journal use and the procedure scheduler do
not use it. Shared locks, storage and transport can still exhaust the original
bounds; no finite refresh guarantees availability under arbitrary delays. The
current timing profile remains synthetic and supplies no physical or hard
real-time guarantee. Verification receipts and remaining work are recorded in
[progress](../PROGRESS.md).
