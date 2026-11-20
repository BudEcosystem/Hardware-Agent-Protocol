"""Publish the completed compact-store results and current project status."""
import json
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-content-store'
report = json.loads((BASE / 'RESULTS.json').read_text())
assert report['passingScopes'] == 19 and report['actualIntegrationScopePassed']
assert report['authorityDatabaseBytes'] == 16132096

rows = []
for item in report['attempts']:
    method = item['targets'][0].rsplit('.', 1)[-1]
    kind = 'Actual 30-case worker' if item['harness'] == 'harness02' else 'Fixture control'
    rows.append(f"| [{item['harness']}](../{item['attempt']}/result.json) | {kind} | `{method}` | Passed |")
text = '''# Completed compact-store results

All 19 scopes pass with exact one-method receipts, zero failures/errors/skips, unchanged inputs and complete scratch retention. Eighteen controls use explicitly substituted workers/semantic results. One process scope executes the actual complete 30-case simulation and original-run import/replay. These results do not constitute a rerun of the earlier full runtime regression.

| Scope | Evidence | Method | Result |
| --- | --- | --- | --- |
''' + '\n'.join(rows) + '''

The actual integration retains all 4,256 scratch files. Its authority database is 16,132,096 bytes, leaving 645,120 bytes under the original 16,777,216-byte single-file limit. All 4,011 evidence references remain, backed by 2,798 exact bodies. The audit verifies original supervisor/authority/handoff associations, complete simulation inspection, and historical replay after configuration and session changes.

See the [aggregate audit](../RESULTS.json), [actual-data audit](../actual-import-audit.json), [review](../REVIEW.md), and [next work](../NEXT.md). Earlier failures remain immutable. Public PAT eligibility, physical qualification and a general capacity/timing guarantee remain unclaimed; the full goal is active.
'''
(BASE / 'results').mkdir()
with (BASE / 'results/README.md').open('x') as stream:
    stream.write(text)

status = '''The [compact evidence-store stage]({prefix}artifacts/implementation/pat-io-content-store/README.md)
passes all **19 new scopes**: 18 fixture controls and an actual bound-worker
integration with the complete **30-case** simulation, independent inspection,
original-run import and exact historical replay after configuration/session drift.
The authority database is **16,132,096 bytes**, leaving **645,120 bytes** under the
unchanged 16 MiB single-file limit. All 4,011 references remain, backed by 2,798
exact bodies; no evidence or cases were dropped. All 261 inherited project files,
the legacy consumer identity and the producer image remain unchanged.

The earlier retention failure remains immutable. The [next work]({prefix}artifacts/implementation/pat-io-content-store/NEXT.md)
is explicit catalog invocation, current-configuration eligibility, and protected
control capacity. Historical success does not authorize a changed device context;
unavailable evidence must not be treated as novelty. Natural-language learning,
persistent Arduino applications, public tooling and actual device, driver and
intelligence-hub providers remain required. Physical qualification is unclaimed;
the full goal is active.
'''
progress = ROOT / 'PROGRESS.md'
old = progress.read_text()
start = old.index('The [real bound-worker import stage]')
end = old.index('**Latest full regression passed:**', start)
progress.write_text(old[:start] + status.format(prefix='') + '\n' + old[end:])
for name in ('docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md'):
    path = ROOT / name
    assert 'The [compact evidence-store stage]' not in path.read_text()
    with path.open('a') as stream:
        stream.write('\n\n' + status.format(prefix='../'))
path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
assert '[compact evidence-store stage]' not in path.read_text()
with path.open('a') as stream:
    stream.write('\n\nThe [compact evidence-store stage](../pat-io-content-store/README.md) passes all 19 scopes, including the complete actual 30-case worker/import/historical-replay integration within the unchanged 16 MiB single-file limit. All original evidence is retained through exact-body sharing. Continue with [explicit catalog invocation and current applicability](../pat-io-content-store/NEXT.md); earlier failures remain immutable. Protected capacity, public qualification/promotion, learning, persistent Arduino applications and actual device/driver/hub providers remain required. The full goal is active.\n')
print(json.dumps(dict(documentationUpdated=True, passingScopes=19, goalStatus='active')))
