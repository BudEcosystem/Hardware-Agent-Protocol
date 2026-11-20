"""Record the consumer candidate and its exact, limited evidence."""
import json
from pathlib import Path
ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-evidence-import'
report=json.loads((BASE/'RESULTS.json').read_bytes())
assert report['storageControlMethodsPassed']==23 and not report['pureReducerWrapperPassed']
assert report['goalStatus']=='active' and not report['realBoundImportVerified']
(BASE/'README.md').write_text('''# Original-run finite-I/O evidence import

The candidate adds a separately pinned host consumer for the original Journal reservation, supervisor authority, committed handoff and archived attempt. It uses bounded no-follow reads and the original writer lease, independently inspects the complete matrix outside Journal transactions, then atomically publishes an immutable evaluation and its evidence closure. Import callers supply only evaluator/run names. Historical lookup and explicit reinspection do not activate a catalog entry or authorize new effects.

All **23 storage/reader/authority control methods pass**. Positive storage fixtures explicitly substitute the worker and semantic oracle. They establish no real worker success. Three additional pure-reducer methods report passing, including independent inspection of an unchanged historical **30-case** capture. That scope retains a wrapper failure because its final count predicate still expected one test. The source-free diagnosis preserves its failed status and original exit code; nothing was rerun.

[Exact results](RESULTS.json), [result notes](results/README.md), [design](DESIGN.md), [review](REVIEW.md), [next work](NEXT.md), [wrapper diagnosis](reducer-harness-diagnosis.json).

The [first frozen source](implementation01/README.md) leaves all253 inherited files unchanged and adds five consumer modules plus23 controls. The [second source](implementation02/README.md) leaves all259 preceding files unchanged and adds only pinned historical data and three pure-reducer tests. Neither changes the producer image. All sources and original attempts remain retained. Review is by the primary agent only.

No actual bound worker is executed in this stage. Real bound import, catalog integration, public tooling, learning, persistent applications, real driver/hub providers and physical qualification remain unfinished. The full HMS goal is active.
''')
(BASE/'REVIEW.md').write_text('''# Review and evidence limits

The public consumer requires the exact installed execution-store object and its shared Journal. It resolves committed identities from that authority; caller paths, result injection and replacement attempts are absent. Successful transport alone is refused by the full semantic inspector. The supervisor archive's unknown unresolved-effects value remains unchanged; only complete independent reduction produces the evaluation's zero unresolved effects.

Files are copied through descriptors anchored at the supervisor root, with bounded directory entries, bytes, regular-file permissions/link checks, original lease device/inode and nonblocking flock ownership. Original input/launch/return bytes and the exact archived output closure are checked. File reads use nonblocking opens so invalid FIFOs cannot block that reader. These checks do not defend against an administrator who can rewrite the entire authority or provide aggregate filesystem quotas.

The store bounds per-document bytes, closure counts, per-run bytes, total document count, encoded data and conservative metadata charges. It checks actual SQL types and lengths before fetching bodies and refuses missing/extra/shadow schema. Publication, receipt chaining and the run association share one transaction; current admin and original bindings are checked again after inspection. Lost replies replay the committed receipt, and missing or corrupt imported data is not reconstructed from producer files.

All23 controls pass, with launch/semantic success explicitly substituted where needed. They cover interrupted publication, drift, changed authority after inspection, active/replaced leases, changed return/output, hardlinks, corrupt retained bodies, bounded reads, schema faults and reentry. The read-only audit checks69 fixture databases and confirms all stored successful outputs are explicitly marked fixtures. There is no actual bound-worker success in this evidence.

The historical complete30-case group passes the pure reducer, and two substitution/incomplete-group methods also report success. Its wrapper returns1 because the inherited final predicate expects one test despite three selected/executed tests. All other recorded final predicates pass. The original failed scope remains failed; see the source-free diagnosis. No data, code or test result is repaired or retried.

Current source identity covers the five consumer modules and their conservative installed semantic/schema/runtime dependencies. It is separate from the unchanged producer identity. Historical configuration/session drift does not rewrite an imported record; an unsupported changed consumer implementation is refused. Historical lookup verifies current retained bytes and authority joins but does not rerun semantics. Explicit reinspection performs full semantic reduction outside the Journal transaction. Catalog admission still needs a separately prepared result plus current byte/authority/environment checks under its scoped read-only verifier.

Further coverage is required for actual bound import, replaced supervisor authority, cross-run/receipt substitution, per-document/aggregate quota boundaries, nonregular/symlink and directory races, multiple-import history and coordinated storage failure. Existing lower-layer controls do not automatically cover the new importer. Public mounting, protected control capacity, general untrusted-process isolation and actual device/driver/hub providers remain outside this candidate. Primary-agent review only.
''')
(BASE/'NEXT.md').write_text('''# Continue toward qualified deterministic reuse

First complete the importer evidence: preserve the diagnosed three-test wrapper failure, correct the count predicate only in a fresh harness, and do not rerun or relabel that original scope. Add the missing importer controls listed in [review](REVIEW.md). Exercise a fresh actual bound-worker/import scenario with its complete original matrix and60-second worker/180-second outer limits. A failed or partial original run stays unavailable; no replacement key, reduced matrix or deadline extension repairs it.

The next catalog contract must carry explicit evaluator/run/configuration identities. The current two-argument callback cannot express the installed I/O invocation. Define a versioned invocation and environment profile, link an imported evaluation through the installed store, and prepare full semantic validation outside admission locks. The scoped catalog verifier may check current retained bytes and prepared results without filesystem/process work inside its transaction. A cold, corrupt or unavailable verifier is an availability refusal, not a novel context or authorization to ask the agent for replacement actions.

Historical evidence and current eligibility remain separate. Reuse must check current endpoint sessions, binding/installation/argument metadata, driver/compiler/evaluator identities, resource generations, grants and the PAT's applicability domain. Learning can propose a new version; it cannot widen an old applicability domain from successful returns alone. Promotion and conflict/suspension need explicit versioned receipts before public mounting.

Retain the [prior handoff failures](../pat-io-execution-handoff/RESULTS.json), including unknown effects, incomplete matrices, masked authority-wrapper errors and retention-scan failures. Their diagnostic gaps require fresh source corrections that preserve separate operation/capture/budget causes; they are not proven timeout causes or successes. Protected CPU/storage/control capacity remains unresolved.

Carry the same resource, permission, operation identity, dependency and reconciliation model through device I/O, drivers and hub services. Hardware/OS capabilities must be advertised by concrete providers. Driver replacement must settle affected users and create new dependency generations; hub restart must preserve independently hosted endpoint reconciliation. Persistent Arduino applications need standing triggers, durable lifecycle/versioning, local loops and outage behavior beyond this finite qualification profile.

Public CLI/MCP and Harness integration, natural-language synthesis, trace learning, persistent controllers, real devices/drivers/hub compute and lifecycle, streams, timing and microscope commissioning remain required. Continue primary-source reading as well. The full HMS goal remains active.
''')
results=BASE/'results'; results.mkdir()
lines=['# Evidence import results','',
    '23 independent control scopes pass. The three-method pure-reducer scope retains a wrapper failure despite complete passing method receipts. No actual bound worker or physical device was executed. All attempts ran once under their original limits.','',
    '[Machine-readable results](../RESULTS.json), [read-only audit source](../audit-results.py), [wrapper diagnosis](../reducer-harness-diagnosis.json), [scope and gaps](../REVIEW.md).','',
    '| Scope | Original status | Methods | Kind |','|---|---|---:|---|']
for row in report['attempts']:
    lines.append('| ['+str(row['scope'])+'](../'+row['attempt']+'/result.json) | '+row['status']+' | '+str(row['counts']['testsRun'])+' | '+('Storage/reader fixture' if row['scope']<24 else 'Legacy-data pure reducer; wrapper count error')+' |')
(results/'README.md').write_text('\n'.join(lines)+'\n')
def summary(prefix):
    return '''The [original-run evidence consumer]('''+prefix+'''artifacts/implementation/pat-io-evidence-import/README.md)
adds bounded archive reading, complete independent reduction and atomic Journal
publication tied to the original configuration, reservation, supervisor and
handoff. All **23 storage/reader controls pass**; positive storage fixtures
explicitly substitute worker and semantic success. Three pure-reducer methods
also report passing, including the unchanged historical **30-case** matrix.
Their scope retains a wrapper failure: its final count predicate expected one
test. The original status, exit code and receipts are preserved without rerun.

All253 inherited production/test inputs remain unchanged; the new consumer has
a separate identity. Historical lookup and explicit reinspection do not provide
fresh PAT eligibility. No actual bound worker runs in this stage, and real bound
import remains unverified. Previous handoff/worker failures remain retained.

[Next work]('''+prefix+'''artifacts/implementation/pat-io-evidence-import/NEXT.md) includes remaining importer
coverage, a real bound import and a versioned catalog invocation/environment
contract. Public mounting, protected capacity, aggregate storage enforcement,
prompt learning, persistent Arduino applications and actual device, driver and
intelligence-hub providers remain required. The full HMS goal is active.
'''
path=ROOT/'PROGRESS.md'; old=path.read_text(); start=old.index('The [durable supervisor handoff candidate]'); end=old.index('**Latest full regression passed:**',start)
path.write_text(old[:start]+summary('')+'\n'+old[end:])
for name in ('docs/prompt-to-pat.md','docs/io-driver-hub-control.md'):
    path=ROOT/name; old=path.read_text(); assert 'The [original-run evidence consumer]' not in old
    path.write_text(old+'\n\n'+summary('../'))
path=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
old=path.read_text(); assert 'pat-io-evidence-import' not in old
path.write_text(old+'\n\nThe [evidence consumer candidate](../pat-io-evidence-import/README.md) adds original-run archive import and atomic evaluation storage. Its23 storage controls pass; its historical30-case reducer reports success within a scope that retains a wrapper count failure. No real bound import is established. Continue the [versioned eligibility and provider work](../pat-io-evidence-import/NEXT.md), preserving every earlier failure and the active full goal.\n')
print(json.dumps(dict(updatedDocuments=8,goalStatus='active')))
