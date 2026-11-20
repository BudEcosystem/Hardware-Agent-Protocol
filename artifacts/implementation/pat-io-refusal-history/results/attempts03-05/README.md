# Checked permission-refusal composition

All **128 distinct selected methods pass across three separate invocations** on
the same frozen source: the retained 72-method operation/parent regression,
27 observation methods, and 29 new refusal methods. There is no single 128-method
invocation or new full748/inherited136 regression result.

| Selection | Test seconds | Harness elapsed seconds | Outcome |
|---|---:|---:|---|
| Retained operation/parent 72 | 147.279 | 166.985 | Pass |
| Observation 27, corrected launcher | 77.593 | 86.547 | Pass |
| Refusal 29 | 56.097 | 65.258 | Pass |

Each successful invocation retains the original 180-second execution deadline
and all evidence, scratch and inventory bounds. [Proof](proof.json) rechecks the
earlier result seal, exact source/harness inventories and loaded/executed method
order, and retains the complete follow-up attempt trees. All 7,060 project files,
7,065 frozen preparation files, six active harness files and 159 external pins
stay unchanged per passing invocation. The follow-up children report 681/683
matched origins and 204/205 refused bytecode reads, with no recorded prohibited
attempts. Compiler and driver receipts match within each successful invocation.
Original empty scratch roots remain retained.

The [earlier combined 56-method selection](../attempts01-02/README.md) reached its
actual execution deadline and was terminated, with only 37 logged `ok`
completions and no terminal test/origin receipts. It remains a failed attempt.
The first 27-method follow-up launcher also remains failed: applying `-I -S -B`
to the parent hid its pinned package metadata, so it stopped before starting a
child or creating scratch. The corrected launch uses the original parent `-B`
and unchanged child `-I -S -B`. No source, test, dependency pin or limit changed.
See the [selection plan](followup-selection-plan.json) and
[launch record](followup-launch-record.json).

The new composition independently derives two supported permission causes from
trusted grant history and preceding state. Parent rejection creates no parent,
child, claim, fence or board effect. Child rejection requires an eligible time
window, runnable parent/prefix, original claims and current endpoint context;
it releases unstarted claims without dispatch, while preserving the fence and
the parent's actual state. Captured error strings alone cannot authorize these
transitions. All private cause handoffs must be consumed by the original event
folds. Standalone APIs preserve their earlier strict refusals.

The composed checker accepts all 26 configured fixtures, including recovery,
active withdrawal and the two pre-effect refusals, and checks 434 snapshots and
1,288 produced samples. Adversaries cover forged grants/reasons, stalled accepted
work, board effects, retained claims, invented handoff, event gaps, parent state
fabrication, missing prior ownership, and precedence at namespace/start deadlines.
Purity/input-immutability tests cover denial and recovery. The inherited 4,235
fixture/manifest files were rechecked against their original captures during
the retained earlier acquisition; this result rechecks that entire sealed result.

This is a primary-agent-reviewed immutable simulation component with retained
read authority. Only two inherited independent folds change; 7,056 other inherited
files remain unchanged. No Runtime, SQL connection, physical device, MCU/emulator,
inference, public service or live HMS/Harness source executes or changes here.
General policy refusals, full read withdrawal, broader timing/fault/auxiliary-actor
coverage, current-source attestation, aggregate storage enforcement and public
qualification remain unfinished. Full attestation, physical-measurement,
independent-outcome and qualification flags stay false.
