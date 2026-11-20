# Source seams used for this design

The copied files below are pinned by [inputs.json](inputs.json). These notes record
selected source inspection, not a new full-file reading claim. Earlier referenced
reviews retain their own reading and execution scopes. The helper's initial copies
were verified again by the primary agent before completing this handoff.

| Copied source | Inspected seam and consequence |
| --- | --- |
| [PAT compiler](inputs/project/hms/pat_compiler.py) | Lines 120–146, 251–282, 325–399: whole-domain schema containment, exact semantics, unchanged absolute windows and caller deadline; no duration/scheduler proof |
| [PAT contracts](inputs/project/hms/pat_contracts.py) | Lines 176–230: 1..16 ordered steps, exact expressions, inclusive syntax bounds and run-budget sums; syntax can admit an empty exclusive start window |
| [Procedures](inputs/project/hms/procedures.py) | Lines 179–349 and 424–500: child admission before child not-before, successful-prefix gate, one new child per tick, completion reconciliation before parent deadline check |
| [Journal](inputs/project/hms/journal.py) | Lines 455–557: exact replay precedes fresh admission, claims/floors at admission, not-before at dispatch, exclusive start/lease upper bounds |
| [Registry](inputs/project/hms/registry.py) | Lines 787–878: live authorization/resource checks and lease capped at admission plus 60000 ms |
| [I/O adapter](inputs/project/hms/synthetic_io_adapter.py) | Lines 54–296: retained dispatch/receipt joins, repeated timing guard, monotonic budget origin, pending tickets, receipt-gated settlement/release |
| [I/O board](inputs/project/hms/synthetic_io_board.py) | Lines 1–55, 90–145, 189–390: idle/active model states, receipt versions, counters, owners/fences, strict duration fit, finish guard before due, reopen cancellation |
| [Installation](inputs/project/hms/synthetic_io_installation.py) | Lines 88–169: handler semantics, proof-derived footprints, schemas and simulation-only activation-count observation |
| [Topology](inputs/project/hms/resource_topology.py) | Lines 202–362: validated alias footprints, scoped dependency proof, ordinary claim closure distinct from lifecycle claims |
| [Fan contracts](inputs/project/hms/pat_simulation_contracts.py) | Lines 1–199 and 233–324: existing finite-domain/matrix approach and fan-specific range/semantic assumptions |
| [Fan worker](inputs/project/hms/pat_simulation_worker.py) | Lines 353–407 and 452–547: scheduler's fan pending-due layout and completion-effect assumptions cannot serve as the I/O oracle |
| [Fan reducer](inputs/project/hms/pat_simulation_evidence.py) | Lines 1–78, 262–440 and 537–614: fan plant/checkpoint shape, ordinal-based single-resource assumptions, event checking, closure bounds and explicit producer-trust limitations |

Other selected copies preserve the surrounding resolver, catalog, Runtime, memo,
API-contract and provider-test context. They are not newly claimed as fully read
in this handoff. No project module was imported and no source was executed.

One attempted combined display exceeded its output budget during preparation.
The required Journal/Registry/adapter/board/installation ranges were displayed
again in bounded calls; the omitted display itself is not evidence of reading.
