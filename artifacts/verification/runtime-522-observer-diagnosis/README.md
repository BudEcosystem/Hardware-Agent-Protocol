# Failed 522-test attempt: observer diagnosis

Attempt `20261106T212220.223800Z-c4b3400474ac` is **failed**: 522 tests ran
in 549.474 seconds, with 520 passing, zero assertion failures, two errors and no
skips. Both errors are `sqlite3.OperationalError: database is locked` in external
test-observer count reads, before the intended prepare request was sent.

| Failed case | Proven stage |
| --- | --- |
| Mixed CLI | First local-fan scenario. `checked('prepare')` appended a history entry, then the count read at frozen `test_multi_cli.py:194` raised before its client-call loop. No prepare or invoke reached HMS. |
| Legacy MCP 2025-11-25 | Namespace and first local-fan prepare succeeded, with `admitted:false`. The count read at frozen `test_procedure_transport.py:128`, called by `prepare` at line 163, failed before the second child prepare (native inspection, `mcp-child:1`). The MCP projection had not yet been entered. |

Both failed cases' authority snapshots contain zero operations, events, claims,
replay keys, endpoint commands, procedures, procedure keys/steps/events and resource
floors. Both original SQLite plants have zero receipts, fences and synthetic
effects. There are no recorded client freshness refusals or endpoint refusal
replies. Daemons and native fixtures exited successfully with empty stderr.

The mixed CLI snapshot contains only HELLO and initial BIND traffic. One final
C2 HELLO has no response in that database snapshot; this does not establish a
timeout. The legacy MCP database contains eight request/reply pairs (seven HELLO,
one initial BIND); its separately captured relay contains nine successful pairs
(eight HELLO, one BIND). Neither has OP or ARM traffic. The captures are not
simultaneous and should not be treated as one atomic transport snapshot.

Separate cases in the same procedure trace passed: CLI restart/resume completed
three children with two native OP handoffs and one persistent SQLite effect;
modern MCP completed two children with one native OP handoff and one persistent
SQLite effect; the paused-native-route case completed one independent operation,
with native synthetic dispatch/effect counters both one. Those separate state
directories do not supply completed work for the failed legacy MCP case. Native
relay handoffs are not independent physical effect measurements.

`evidence-pins.json` pins 268 existing immutable evidence files. The diagnosis
verified all 112 before snapshots, all 112 after snapshots, all 25 recorded output
files, both original failure manifests and their entire closures, and the copies
of those closures retained by the attempt. Before/after source digest sets match;
the compiler identity files match; the receipt's stability flags are true.
No changing live source was compared. Existing snapshots were not duplicated.

`current-pointer-at-diagnosis.json` is a byte-for-byte copy taken while the current
pointer still named this failed attempt and its matching receipt digest. It is
historical evidence, not a promise that the mutable pointer still names this run.
`diagnosis.json` records exact stages, counts, packet classifications, hashes and
the completed separate cases. `diagnose.py` performs read-only SQLite inspection
and uses pure codecs from the retained source tree; it executes no tests, runtime,
native fixture or device, and refuses to overwrite diagnosis outputs.

The evidence identifies observer failures, but does not identify the exact SQLite
writer, lock holder, commit duration or scheduling history. It does not establish
a production timing defect or a successful full-suite qualification. The observer
repair is a separate change. This lane changes no production/test sources and
preserves every original failure artifact.
