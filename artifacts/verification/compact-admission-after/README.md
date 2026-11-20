# Bounded fresh-invoke observation: targeted proof

The 25 targeted original-native/virtual-clock tests passed in 42.225 seconds.
All 63 copied input files were verified before and after execution. No full or
broad regression suite was run in this lane. `run.log` is the actual unittest
output; `run.json` retains the actual test trace. The runner imports HMS and the
test fixtures only from `inputs/` and refuses to overwrite its output files.

The production change is limited to four files:

- `journal.py`: internal `PresenceAgeExpired` marker, preserving the public
  `DEVICE_UNAVAILABLE` code.
- `registry.py`: that marker requires an existing matching adapter/session row,
  known expiry and current static authorization, binding and installed support.
- `runtime.py`: ordinary submit first; only that narrow marker can lead to a
  normal submit recheck under route-lock then Journal-mutex order, one observation
  refresh, then ordinary submit of exactly the same canonical bytes.
- `endpoint_binding.py`: the refresh gate requires an already installed,
  catalog-ready, fault-free compact route with a boot/context and stream, outside
  any active transaction. It uses HELLO without initialization or worker dispatch.

The preserved before probe showed one other route's eight commit pauses aging
the target past its 1000 ms TTL. The same controlled delay now leads to exactly
one target HELLO and admission of the original request. The test asserts unchanged
grants/bindings and zero added endpoint dispatch/effects during observation; the
subsequent ordinary worker sends exactly one OP and produces one synthetic effect.
No OP, ARM or BIND is sent by the fresh-invoke observation path.

The final-publication-delay case still refuses after one HELLO with no operation,
claim, command or replay-key allocation. The implementation does not widen TTLs,
change absolute deadlines, restamp original observations or loop until success.
Live preconditions and resource conflicts may still refuse after the observation.

Other tests assert no extra endpoint I/O for retained accepted/terminal/conflicting
replay, outcome-unknown replay after restart, invalid or expired authority, changed
binding/session/adapter, absent presence, unavailable/unready/faulted route, invalid
wall/monotonic clock, and missing general invoke, exact action or read permission.
Thread barriers verify concurrent same-key admission/conflict and revocation while
waiting for the route lock. Deadline and namespace expiry during refresh allocate
nothing. Prepare and direct Journal submission remain outside this automatic path;
managed procedure admission was not changed.

`input-pins.json` pins the isolated 63-file execution closure, including original C
fixture binary/provenance and copied source/data. `live-source-pins.json` identifies
the live HMS source snapshot copied before execution, including other agents' PAT
files at that instant. Only the four production files above and the new targeted
test are this lane's changes. The isolated tree prevents concurrent PAT work from
changing what these tests import; this is not a claim that later PAT sources were
tested here. `environment-pins.json` records the installed Python executable and
validation-library file closures. `production.diff` compares this lane's four
production files to the frozen before tree.

The independently reviewed source shape had no identified replay/auth/lock blocker;
the reviewer did not run these tests. This proof executes only original native
simulation fixtures, with synthetic synchronized clocks and logical elapsed-time
injection after real SQLite commits. It does not measure filesystem latency or
qualify a physical clock, controller, device or timing-isolation guarantee.

The original failed-459 case remains unattributed: these tests prove a possible
availability mechanism and a bounded improvement, not the missing historical
presence/commit chronology. All earlier receipts and frozen before evidence remain
unchanged.
