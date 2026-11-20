"""Reconcile bounded encoding checks and current deadline evidence."""
from pathlib import Path
ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-page-encoding'
assert not (B / 'results/index.json').exists()

path = ROOT / 'PROGRESS.md'; text = path.read_text()
assert text.count('The current [group-history stage]') == 1
text = text.replace('The current [group-history stage]', 'The preceding [group-history stage]')
anchor = 'The separate [qualification supervisor rebase]'
assert text.count(anchor) == 1
text = text.replace(anchor, '''The current [page-encoding stage](artifacts/implementation/pat-io-page-encoding/results/README.md)
passes **118 distinct methods**: 117 pure checks and the actual record-cutoff
method. A bounded per-engine memo reuses exact canonical table-page bytes after
the unchanged current SQL validation. Keys include profile, stream/domain, table,
columns, offset, total row count and exact typed cells. The 128-entry/1MiB encoded
byte capacity is separate from unchanged evidence ceilings. All current schema,
count, size, storage-class, blob-validation and row reads remain; source comparison
confirms unchanged capture, reservation and durable-storage method bodies.

Ten focused methods cover bytes/digests, scalar distinctions, changed inputs,
detachment, cache eviction, both streams, budget precedence and retained failed
writes. The actual cutoff retains the same 977,425 raw bytes as the preceding
encoding stage. All four attempts preserve 227 project/230 frozen inputs, six
active harness inputs, 159 external pins, matched origins and within-attempt
compiler/driver identity. Historical fixture-only inputs are explicitly excluded
from this worker closure, with their original immutable pins retained.

Fresh GPIO still stops after 23/30 cases at the original capture deadline,
before independent inspection. Its active permission-before-dispatch child is
rejected, parent failed, and receipt/effect/claim/owner absent. The diagnostic
profile stops after 11/30 cases and preserves an accepted child, running parent
and one claim in the not-before-boundary case. No retained state is reconciled
or replaced. PWM harness04 is unexecuted after the GPIO gate fails.

The profile records 16,976 canonical calls / 31.450 cumulative seconds and
substantial overlapping runtime setup, installation/topology and cell-validation
costs. Whole-method process CPU/wall totals are 55.803/68.217 seconds, including
pre-run setup and profiler overhead. These observations establish neither a
performance improvement nor the cause of run-to-run variation. The next source
should address repeated pure snapshot/installation work while retaining exact
types, detachment, current SQL/authority reads and every original bound. Complete
fresh capture/inspection, trusted process/run association, aggregate enforcement,
public qualification, learning, persistent applications and real providers remain
unfinished. Live HMS and the adjacent Harness are unchanged; the goal is active.

''' + anchor)
path.write_text(text)

path = ROOT / 'docs/prompt-to-pat.md'; text = path.read_text()
anchor = 'An operator says, for example,'
assert text.count(anchor) == 1
text = text.replace(anchor, '''The subsequent [page-encoding stage](../artifacts/implementation/pat-io-page-encoding/results/README.md)
passes 118 distinct pure/cutoff checks. Exact page-byte reuse keeps current SQL
validation and durable writes, but fresh GPIO still stops after 23/30 cases at
the original deadline. A diagnostic profile stops after 11 cases and retains an
accepted child, running parent and one claim. Neither reaches inspection; PWM
remains unexecuted. Runtime setup and repeated installation/topology encoding
remain substantial costs. This supplies no new PAT qualification or promotion
evidence; the complete historical inspection above remains a separate result.

''' + anchor)
path.write_text(text)

path = ROOT / 'docs/io-driver-hub-control.md'; text = path.read_text()
text += '''
The subsequent [page-encoding stage](../artifacts/implementation/pat-io-page-encoding/results/README.md)
passes 118 distinct pure/cutoff methods. Bounded exact page encodings retain all
current SQL/authority reads, validation, accounting and durable-write behavior.
Fresh GPIO still stops after 23 cases, before inspection. The diagnostic profile
stops after 11 and retains one accepted child, running parent and claim; PWM is
unexecuted. Runtime setup and installation/topology processing remain significant
measured costs. Complete current capture, driver/hub lifecycle execution and
public qualification remain required.
'''
path.write_text(text)

path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'; text = path.read_text()
lines = text.splitlines(); matches = [i for i, line in enumerate(lines) if line.startswith('| Group budgets and retained evidence |')]
assert len(matches) == 1
lines[matches[0]] = '| Group budgets and retained evidence | Complete [historical group inspection](../pat-io-group-history/results/README.md) remains available; the subsequent [page-encoding stage](../pat-io-page-encoding/results/README.md) passes 118 pure/cutoff methods and preserves exact page bytes, live SQL checks and durable writes | Latest fresh GPIO stops after 23/30 cases; the diagnostic profile stops after 11 with an accepted child, running parent and one claim. PWM is unexecuted. Address repeated pure setup/encoding costs, then complete fresh inspection, trusted process/run association and actual aggregate enforcement |'
text = '\n'.join(lines) + '\n'
anchor = 'Finite I/O qualification still does not implement'
assert text.count(anchor) == 1
text = text.replace(anchor, '''The subsequent exact page-encoding candidate passes its 117 pure checks and
actual record cutoff but still misses the current capture deadline after 23
cases. Its separate instrumented run stops after 11 and retains unresolved
accepted work and one claim. Neither reaches inspection; PWM is unexecuted.
The current profile points to runtime setup, installation/topology processing
and canonical encoding. Further work must preserve exact scalar types, detached
inputs, current source/validator association and all mutable authority reads.
No timing ceiling, required case or effect/storage limit may be widened to
replace the missing complete result.

''' + anchor)
path.write_text(text)
print('Reconciled current encoding/capture evidence across four documents; goal remains active.')
