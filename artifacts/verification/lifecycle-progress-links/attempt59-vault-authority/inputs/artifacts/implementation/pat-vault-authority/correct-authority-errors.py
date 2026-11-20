"""New source copy: preserve authority refusals across the held-vault boundary."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = BASE / 'implementation01'
NEW = BASE / 'implementation02'

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())

def dump(path, value):
    write(path, json.dumps(value, indent=2) + '\n')

assert hashlib.sha256((OLD / 'index.json').read_bytes()).hexdigest() == 'cc5d2f6b337645f2483b94e46e9559ead5f6c905bd8b92231c67138dd5f1c6ce'
failed = BASE / 'harness13/attempts/attempt01'
result = json.loads((failed / 'result.json').read_bytes())
assert result['childState'] == 'exited' and result['counts']['failures'] == 1 and result['counts']['errors'] == 0
assert '"CONFIGURATION_CHANGED" does not match "PAT_EVIDENCE_VAULT_INVALID"' in (failed / 'output.log').read_text()
NEW.mkdir()
for row in json.loads((OLD / 'index.json').read_bytes())['files']:
    source = ROOT / row['path']; raw = source.read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    if not source.is_relative_to(OLD / 'project') and source.name != 'baseline-inputs.json': continue
    relative = source.relative_to(OLD)
    write(NEW / relative, raw)
source_path = NEW / 'project/evidence_authority/store.py'
before = source_path.read_text()
after = before.replace('from hms.journal import Journal\n', 'from hms.journal import Journal, JournalError\n')
assert after.count('with self.vault.snapshot(') == 3
after = after.replace('with self.vault.snapshot(', 'with self._snapshot(')
marker = '    def _published(self, context, key, state):\n'
helper = '''    @contextmanager
    def _snapshot(self, intent_digest, binding_digest):
        # The byte-vault normalizes exceptions thrown into its context manager.
        # Authority refusals belong to this importer. Let the vault validate and
        # release its held snapshot normally, then re-raise the original refusal.
        # A vault expiry/cleanup failure still takes precedence; nothing commits
        # or becomes eligible because an authority exception was deferred here.
        refusal = None
        with self.vault.snapshot(intent_digest, binding_digest) as snapshot:
            try:
                yield snapshot
            except JournalError as error:
                refusal = error
        if refusal is not None:
            raise refusal

'''
assert marker in after
after = after.replace(marker, helper + marker)
ast.parse(after)
source_path.write_text(after)
write(NEW / 'authority-errors.patch', ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile='implementation01/evidence_authority/store.py', tofile='implementation02/evidence_authority/store.py')))
test_path = NEW / 'project/tests/test_vault_authority.py'
before_test = test_path.read_text()
new_test = '''
    def test_revocation_after_seal_preserves_authority_refusal(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_evidence_seal':
                self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_fixture()
        self.assertEqual(self.sizes_evidence(), (1, 0, 1)); self.assertEqual(self.sizes(), (1, 1))
        self.assertIsNone(self.vault._lease); self.assertFalse(self.vault._db.in_transaction)
        self.assertFalse(self.db.in_transaction)
        self.emit('revoked-after-seal', dict(intents=1, publications=0, manifests=1,
            authorityErrorPreserved=True, leasesReleased=True, workerExecuted=False))
'''
after_test = before_test + new_test
ast.parse(after_test); test_path.write_text(after_test)
write(NEW / 'authority-error-test.patch', ''.join(difflib.unified_diff(before_test.splitlines(True), after_test.splitlines(True),
    fromfile='implementation01/tests/test_vault_authority.py', tofile='implementation02/tests/test_vault_authority.py')))
for row in json.loads((NEW / 'baseline-inputs.json').read_bytes())['files']:
    path = NEW / 'project' / row['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
write(NEW / 'README.md', '# Authority refusal correction\n\n'
    'All 280 inherited project files remain exact. The independent vault is unchanged. '
    'Only the new importer adds a context boundary that preserves authority JournalError refusals after normal snapshot validation/release; vault expiry or cleanup failure still takes precedence. '
    'The original 19 methods are unchanged, and one post-seal revocation method is added. '
    'The earlier configuration-change assertion failure remains retained; no state is repaired or reset.\n')
dump(NEW / 'correction.json', dict(previousSource='implementation01', previousFailure='harness13/attempts/attempt01',
    productionChanged=['evidence_authority/store.py'], inheritedFilesUnchanged=280,
    previousMethodsUnchanged=19, newMethods=1, standaloneVaultUnchanged=True,
    correction='Preserve authority refusal after held snapshot cleanup; vault expiry and cleanup failures still refuse',
    noFailedStateReset=True, noBoundsChanged=True))
files = []
for path in sorted(NEW.rglob('*')):
    if path.is_file():
        raw = path.read_bytes(); files.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
dump(NEW / 'index.json', dict(scope='Typed authority-refusal correction; complete current-source control selection still requires verification', files=files))

target_prefix = 'test_vault_authority.VaultAuthorityTests.'
selections = [
    [target_prefix + 'test_configuration_change_after_seal_prevents_publication', target_prefix + 'test_revocation_after_seal_preserves_authority_refusal'],
    [target_prefix + 'test_expired_snapshot_before_commit_rolls_back_publication'],
]
template = BASE / 'harness13'
for number, targets in enumerate(selections, 18):
    folder = BASE / ('harness%02d' % number); folder.mkdir()
    for row in json.loads((template / 'index.json').read_bytes())['files']:
        path = template / row['path']; raw = path.read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        if row['path'] in ('attempt_child.py', 'run_attempt.py', 'targets.json', 'README.md', 'SCOPE.md'): continue
        write(folder / row['path'], raw)
    child0 = (template / 'attempt_child.py').read_text(); parent0 = (template / 'run_attempt.py').read_text()
    start = child0.index('CONTROL_TARGETS = '); end = child0.index('\n', start)
    child = child0[:start] + 'CONTROL_TARGETS = ' + repr(targets) + child0[end:]
    child = child.replace("len(config['targets']) != 2 or len(set(config['targets'])) != 2", "len(config['targets']) != %d or len(set(config['targets'])) != %d" % (len(targets), len(targets)))
    child = child.replace("counts['testsRun'] == 2 and", "counts['testsRun'] == %d and" % len(targets))
    parent = parent0.replace("SOURCE = BASE / 'implementation01'", "SOURCE = BASE / 'implementation02'")
    parent = parent.replace('len(targets) == len(set(targets)) == 2', 'len(targets) == len(set(targets)) == %d' % len(targets))
    parent = parent.replace("counts['testsRun'] == 2 and", "counts['testsRun'] == %d and" % len(targets))
    ast.parse(child); ast.parse(parent)
    for name, original, corrected in [('attempt_child.py', child0, child), ('run_attempt.py', parent0, parent)]:
        write(folder / name, corrected)
        write(folder / 'references' / ('pre-authority-correction-' + name), original)
        write(folder / ('authority-correction-' + name + '.patch'), ''.join(difflib.unified_diff(original.splitlines(True), corrected.splitlines(True), fromfile='harness13/' + name, tofile=folder.name + '/' + name)))
    dump(folder / 'targets.json', targets)
    write(folder / 'README.md', '# Authority-refusal correction controls\n\n'
        '[Targets](targets.json), [scope](SCOPE.md), [corrected source](../implementation02/README.md).\n')
    write(folder / 'SCOPE.md', '# Focused correction selection\n\n'
        '%d methods on implementation02. Checks specific authority refusal after sealing and/or unchanged snapshot-expiry rollback. '
        'This is not the full 20-method corrected-source selection. Parent 180 seconds, child 120 CPU seconds, '
        '512 MiB address space, 16 MiB/file, 256 MiB scratch, 4 MiB output and 64 SQLite connections remain unchanged. '
        'All state is fresh and retained. No worker, network or physical execution; declared substitute semantic oracle.\n' % len(targets))
    files = []
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            raw = path.read_bytes(); files.append(dict(path=path.relative_to(folder).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    dump(folder / 'index.json', dict(scope='Focused authority-error correction, not complete production qualification', files=files))
print(json.dumps(dict(source='implementation02', indexSha256=hashlib.sha256((NEW / 'index.json').read_bytes()).hexdigest(),
    correctedScopes=['harness18', 'harness19'], previousFailureRetained=True)))
