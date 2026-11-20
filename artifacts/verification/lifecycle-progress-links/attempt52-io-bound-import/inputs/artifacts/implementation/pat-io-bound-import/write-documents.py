"""Publish exact integration evidence without converting storage failure to pass."""
import json
from pathlib import Path
ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'
report=json.loads((BASE/'RESULTS.json').read_bytes())
assert report['realOriginalBoundImportVerified'] and not report['actualIntegrationScopePassed']
assert report['newFixtureControlsPassed']==5 and report['goalStatus']=='active'
(BASE/'README.md').write_text('''# Real bound-worker evidence import

One actual supervised worker completed the original **30-case** matrix. The unchanged consumer independently inspected it, atomically imported4011 evidence documents, and returned the same receipt after configuration and endpoint-session drift. The original supervisor authority, reservation, handoff, request, attempt and captured bytes are independently joined by the read-only audit. No worker or semantic oracle was substituted in this method, and source-device business state stayed unchanged.

The enclosing scope **failed retention**. Its authority database grew to17,591,296 bytes, exceeding the unchanged16,777,216-byte single-file limit by814,080 bytes. The passing method receipt does not make the scope pass. The original failure, raw database, process receipts and evidence remain retained. A separate forensic copy stores the oversized database in8MiB-or-smaller chunks without changing or repairing it.

All **five new fixture controls pass**: replacement supervisor, distinct import history, rehashed cross-run substitution, forged receipt chain and32769 rows exceeding the32768-document bound before body fetch. Their successful worker/semantic results remain explicit fixtures. One earlier harness-preparation failure started no child or worker and is retained separately.

[Exact results](RESULTS.json), [per-scope receipts](results/README.md), [forensic audit](forensic01/audit.json), [forensic manifest](forensic01/raw-manifest.json), [review](REVIEW.md), [design](DESIGN.md), [next work](NEXT.md).

All259 inherited project files remain unchanged. The [new source](implementation01/README.md) adds only two test modules; the producer image remains262 files. Review is by the primary agent only. The completed worker was observed once; previous deadline/retention failures are not repaired or contradicted by this sample.

An [in-memory deduplication model](deduplication-sizing.json) reconstructs all4011 rows byte-for-byte and estimates1,463,296 fewer allocated bytes after reference/body index overhead, leaving649,216 bytes below the file limit for this dataset. This is not a compact-store implementation, migration or passing retention result. Public catalog eligibility, prompt learning, persistent controllers and real device/driver/hub providers remain unfinished. The full HMS goal is active.
''')
(BASE/'REVIEW.md').write_text('''# Evidence, failures and remaining limits

The real integration used the actual installed source authority and current configuration to reserve one run, bind one durable supervisor authority/attempt, launch one original worker, inspect the complete matrix and import the result. Its code patches only a diagnostic checkpoint. It does not patch launch, semantic inspection or importer output. Configuration/session drift is followed by reopen and exact historical replay with launch, planning and worker-directory rereading explicitly forbidden. This proves historical replay for this run, not current eligibility under changed configuration.

The actual worker's captured output is3936 files and14,608,242 bytes. The consumer retains4011 documents totaling15,355,663 bytes, including trusted original controls/inputs and derived inspections. The final authority database is17,591,296 bytes,814,080 over the scope's16MiB limit. The original worker/group60-second and outer180-second bounds remain unchanged; no matrix, evidence, effect, byte or time ceiling was widened. The method reports success, but retention fails and the scope remains failed.

The read-only forensic collector reacquires actual owner and writer leases, checks the original writer device/inode, preserves all4255 original files totaling36,807,069 bytes, and hashes source bytes before/after. It stores the oversized database as three chunks, each at most8MiB. Concatenated hashes match the original. This is separate diagnostic retention; it does not reinterpret the failed harness limit. It opens source databases only in read-only immutable mode and executes no project runtime or worker code.

The audit verifies every stored evidence body and the exact imported closure against the original worker files, joins source Journal reservation/handoff with the actual version2 supervisor, checks the historical replay receipt, and verifies all262 producer-image files against frozen project/selected dependency origins. The imported evaluation contains30 inspected cases and zero unresolved simulated effects. The supervisor's original unknown-effects field remains unchanged. Physical objective verification and fresh catalog eligibility remain false/unclaimed.

Five new controls pass with explicit fixture provenance. Two distinct real reservation/handoff keys receive distinct fixture attempts and import receipts. Rehashing a borrowed handoff control into the second evidence closure still refuses on the authority association. A forged receipt chain, replacement supervisor and document-count excess also refuse without repair. These checks do not establish physical execution or all storage/lifecycle failure coverage.

The first preparation helper incorrectly expected a literal target list in a process-child template that obtains its list from the reviewed parent configuration. A launch was then invoked before that preparation failure had been inspected; it refused the missing child file. No child, supervisor admission or worker started. The original partial harness/attempt is retained; complete fresh harnesses were inspected before execution. A later source-free audit reader assumed that the never-started receipt contained a null pid, but it omits that field. Its original source and failure diagnosis remain, and a corrected reader uses an optional lookup only in that branch. No project test was rerun.

Exact duplicate bodies total1,717,100 bytes across1213 references. The fresh in-memory normalised layout measures body/reference/index allocation and reconstructs every row unchanged. Its estimated authority size is16,128,000 bytes, with649,216 bytes of headroom. Actual transaction history, schema growth, freelist/pointermap pages and sidecars can differ. A new store must retain expanded-data/count/work bounds, corruption checks, atomicity, exact replay and explicit version compatibility. Deduplication alone supplies neither a general16MiB capacity guarantee nor protected control capacity.

Previous worker deadlines, masked challenge errors, retention-scan failures and the three-test reducer-wrapper failure remain immutable. This sample establishes no timing guarantee. No public qualification service, physical provider, MCU/emulator, live inference, acquired controller/research execution or adjacent Harness mutation occurred. Primary-agent review only.
''')
(BASE/'NEXT.md').write_text('''# Compact exact evidence, then qualified reuse

The actual original-run worker/import/replay path now has a complete method receipt and independent authority/byte audit. Its enclosing scope fails because the resulting authority database exceeds the original16MiB file limit. Preserve that failure and all original limits. Do not truncate evidence, reduce the30-case matrix, silently accept larger files or reclassify the old run.

Implement an explicitly versioned content-addressed evidence layout in a separate host package. Store each exact body once and retain every run/path reference. Preserve original bytes and their digest, canonical controls, full expanded closure and independent inspection. The measured dataset has1213 duplicate references; the in-memory layout estimates1,463,296 fewer allocated bytes after index overhead. Treat this as a design input, not a passing implementation.

Bound both unique stored bodies and expanded per-run/store work, document/object/reference counts, actual SQL types and sizes, metadata charges and total retained capacity. A missing body, orphan object, mismatched digest/length, changed reference, schema shadow or conflicting existing body must refuse without repair. Publishing objects, references, receipt and run association must be one transaction. A lost commit reply resolves the same receipt. Reusing an existing body must verify its actual bytes; a mutable digest column is insufficient.

Keep the frozen legacy consumer usable under its explicit version and authority. Do not silently migrate, reset or rewrite its old evidence. New compact-store construction and compatibility must be explicit. Adding host storage must not change the producer image unnecessarily. Test multi-run shared bodies, rollback/lost replies, corruption/orphans, quotas, schema faults, historical drift and cross-run controls. Then exercise a fresh actual integration under the original matrix, effect, worker/time/file/storage limits. Do not retry an old logical run as a repair.

Allocated SQLite size and protected control capacity need separate admission/operational work. Exact deduplication cannot guarantee arbitrary high-entropy inputs fit16MiB, and retaining evidence in the shared authority can consume control capacity. Advertise concrete supported capacity, distinguish expansion/encoded/allocated accounting, preserve bounded control/reconciliation under logging/storage failure, and measure the complete path before public mounting.

Continue with the [versioned catalog invocation/environment contract](CATALOG-NEXT.md). Prepare full semantic validation outside admission locks; retain current-byte, authority/configuration and evaluator checks for fresh promotion/reuse. Cold or unavailable evidence is an availability refusal, not novelty or permission to synthesize replacement effects.

The complete goal still includes natural-language applications, trace-based learning, deterministic PAT reuse, persistent Arduino controllers, public CLI/MCP and Harness integration, real device I/O, driver and intelligence-hub lifecycle/compute providers, streams, clocks/timing and microscope commissioning. Continue primary-source research. No real hardware or physical objective is qualified by this stage; the full HMS goal remains active.
''')
results=BASE/'results';results.mkdir()
lines=['# Bound import results','',
    'One preparation attempt started no child or worker. Six reviewed scopes executed once: five fixture scopes pass; the real worker/import method reports success but its enclosing scope fails retention. All original bounds and failures remain.','',
    '[Exact report](../RESULTS.json), [corrected read-only audit](../audit-results-current.py), [forensic evidence](../forensic01/audit.json), [storage sizing](../deduplication-sizing.json), [review](../REVIEW.md).','',
    '| Scope | Original status | Evidence |','|---|---|---|',
    '| [Preparation](../harness01/attempts/attempt01-real-import/result.json) | failed, not started | No test child/worker |']
for row in report['attempts']:
    lines.append('| ['+row['harness']+'](../'+row['attempt']+'/result.json) | '+row['status']+' | '+('Real30-case worker/import/replay method reported success; file retention failed' if row['harness']=='harness02' else 'Explicit authority/history/storage fixture passed')+' |')
(results/'README.md').write_text('\n'.join(lines)+'\n')
def summary(prefix):
    return '''The [real bound-worker import stage]('''+prefix+'''artifacts/implementation/pat-io-bound-import/README.md)
has a complete method receipt for the original **30-case** worker, independent
inspection, atomic evidence import and exact replay after configuration/session
drift. The source authority, supervisor, handoff and captured bytes are audited.
All **five new importer fixture controls pass**; all259 inherited files are unchanged.

The actual integration scope **fails retention**: its17,591,296-byte authority
database exceeds the unchanged16MiB file limit by814,080 bytes. The original
failure is retained, with a separate bounded-chunk forensic copy. One preparation
failure started no child/worker. No original scope is rerun or reclassified.

An exact-deduplication sizing model reconstructs every row unchanged and estimates
1,463,296 fewer allocated bytes after index overhead; it is not an implemented
store or passing retention result. [Next work]('''+prefix+'''artifacts/implementation/pat-io-bound-import/NEXT.md) is versioned compact evidence
storage, protected capacity and catalog eligibility. Prompt learning, persistent
Arduino applications, public tooling and actual device/driver/intelligence-hub
providers remain required. Physical qualification is unclaimed; the full goal is active.
'''
path=ROOT/'PROGRESS.md';old=path.read_text();start=old.index('The [original-run evidence consumer]');end=old.index('**Latest full regression passed:**',start)
path.write_text(old[:start]+summary('')+'\n'+old[end:])
for name in ('docs/prompt-to-pat.md','docs/io-driver-hub-control.md'):
    path=ROOT/name;old=path.read_text();assert 'The [real bound-worker import stage]' not in old
    path.write_text(old+'\n\n'+summary('../'))
path=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';old=path.read_text();assert 'pat-io-bound-import' not in old
path.write_text(old+'\n\nThe [real bound-worker import stage](../pat-io-bound-import/README.md) verifies a complete30-case worker/import/historical-replay method and five new fixture controls. The enclosing actual scope retains a16MiB single-file retention failure; its authority database is814,080 bytes over. The [next storage and eligibility work](../pat-io-bound-import/NEXT.md) must retain all evidence and original limits, then connect the versioned catalog. Earlier failures remain; the full goal is active.\n')
print(json.dumps(dict(goalStatus='active',actualIntegrationScopePassed=False,actualBoundImportVerified=True)))
