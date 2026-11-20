"""Freeze reviewed source and prepare the bounded52 selection, no project imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-conflict-history'
SOURCE=BASE/'implementation01'; OLD=ROOT/'artifacts/implementation/pat-io-combined-matrix/harness01'; NEW=BASE/'harness01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as stream: stream.write(json.dumps(v,indent=2)+'\n')
old_project=ROOT/'artifacts/implementation/pat-io-combined-matrix/implementation01/project'
changed=[]; unchanged=0
for row in read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs']:
    rel=(ROOT/row['path']).relative_to(old_project); p=SOURCE/'project'/rel
    if p.stat().st_size==row['bytes'] and sha(p)==row['sha256']: unchanged+=1
    else: changed.append(rel.as_posix())
assert unchanged==7059 and len(changed)==5
write(SOURCE/'source-review.json',dict(scope='Primary-agent source and test review; no independent helper available.',
    inheritedInputsUnchanged=unchanged,changedFiles=changed,newFiles=['hms/pat_io_conflict_capture.py','hms/pat_io_conflict_history.py','tests/test_pat_io_conflict_history.py'],
    reviewed=['Separate0.2 record profile; legacy parsing remains fail closed by default.',
      'One deterministic first-argument conflict with all original identifiers, original plan retained and unchanged operation ceilings.',
      'Independent request reconstruction, trusted read/namespace/parent context, unchanged execution and configuration snapshots, private consumed parent-fold handoff.',
      'Expired wall time is not namespace pruning; read authority precedes existing-key conflict.',
      'Nine retained runtime cases, fifteen rehashed attacks, two private guard checks, pure reader veto check, four unchanged legacy cases and39 unchanged transcript tests.',
      'No provider/runtime/compiler/journal business logic or historical fixtures changed. Full fault matrix, attestation, outcome and qualification remain incomplete.'],
    independentReview=False,projectExecutionDuringPreparation=False,releasedBy='primary-agent'))
(SOURCE/'README.md').write_text('# Recorded same-key conflict extension\n\nThis isolated candidate adds one explicit v0.2 configured-trial conflict probe\nand an independent paired-history checker. All original command identities and\neffect limits remain fixed. Five recording/reader modules change;7059 inherited\nfiles and all historical fixtures remain unchanged. Source review is retained\nin [source-review.json](source-review.json). No qualification result is implied.\n')
rows=[]
for p in sorted(SOURCE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix=='.py': ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7070
write(SOURCE/'index.json',dict(scope='Frozen original conflict capture/checker source; no project execution during preparation.',files=rows))
source_pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='987740d8376199a0ac2623cfa5f107e3985220b3a439a5f831cfa14d06cc112e'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path']; assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
NEW.mkdir(exist_ok=False); (NEW/'references').mkdir(); borrowed=[]
for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
    p=OLD/name; relative='references/'+('matrix61-' if '/' not in name else '')+p.name
    shutil.copyfile(p,NEW/relative); borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
write(NEW/'borrowed-inputs.json',borrowed)
targets=[]
for module,cls,count in [('test_pat_io_transcript','IoTranscriptTests',39),('test_pat_io_conflict_history','IoConflictHistoryTests',9)]:
    tree=ast.parse((SOURCE/'project/tests'/(module+'.py')).read_text()); selected=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    names=sorted(module+'.'+cls+'.'+n.name for n in selected.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
    assert len(names)==count; targets+=names
legacy=['test_configuration_gpio_retains_all_tables_and_legacy_semantics','test_configuration_pwm_retains_typed_bindings_and_routes',
        'test_configuration_reopen_retains_session_and_epoch_changes','test_configuration_sixteen_steps_stay_within_original_shared_limits']
targets+=['test_pat_io_configuration_capture.IoConfigurationCaptureTests.'+n for n in legacy]
assert len(targets)==len(set(targets))==52
write(NEW/'targets.json',dict(testCount=52,targets=targets))
for name in ['run_attempt.py','attempt_child.py']:
    before=(OLD/name).read_text(); after=before.replace('CombinedMatrix61','ConflictHistory52').replace('matrix61','conflict52')
    after=after.replace('io-combined-matrix','io-conflict-history').replace('0a34336874ffe2c3d65301e40adf2b7a9328ddb08a074e02e4e777b9528bf78a',source_pin)
    after=after.replace('7067','7070').replace('7064','7067').replace('!= 61','!= 52').replace('== 61','== 52').replace("'expectedTests': 61","'expectedTests': 52")
    if name=='run_attempt.py':
        start=after.index("                sum(name.startswith('test_pat_io_contracts")
        end=after.index(":\n            raise ValueError('Closed",start)
        after=after[:start]+"                sum(name.startswith('test_pat_io_transcript.IoTranscriptTests.') for name in targets['targets']) != 39 or\n                sum(name.startswith('test_pat_io_conflict_history.IoConflictHistoryTests.') for name in targets['targets']) != 9 or\n                sum(name.startswith('test_pat_io_configuration_capture.IoConfigurationCaptureTests.') for name in targets['targets']) != 4)"+after[end:]
        after=after.replace("'externalRoots': external_before['roots'], 'expectedInputs': before,", "'scratch': str(scratch), 'externalRoots': external_before['roots'], 'expectedInputs': before,")
        after=after.replace('<= 600','<= 180')
        after=after.replace('Independent conflict52 pure selection for combined qualification preflight and inherited domain/timing validation; no Runtime construction, SQLite connection, network, native endpoints, model or hardware execution.',
            'Thirteen original private SQLite runtime simulations plus39 inherited pure transcript tests; no network, physical endpoint, MCU, inference or live service.')
        after=after.replace('io-conflict-history-pure-attempt','io-conflict-history-attempt')
    else:
        after=after.replace('import os\n','import os\nimport re\n')
        after=after.replace('prohibited = []','prohibited = []\ncurrent_test = None\nsqlite_connections = []\nscratch = Path(config[\'scratch\']).resolve()')
        after=after.replace("'os.posix_spawn', 'sqlite3.connect', 'sqlite3.connect/handle'", "'os.posix_spawn'")
        after=after.replace('forbids network, subprocesses and SQLite connections','forbids network and subprocesses')
        hook="""    if event == 'sqlite3.connect':
        raw = os.fsdecode(os.fspath(args[0])); path = Path(raw).resolve()
        valid = (type(current_test) is str and current_test in config['targets'] and
            current_test.startswith(('test_pat_io_conflict_history.', 'test_pat_io_configuration_capture.')) and
            Path(raw).is_absolute() and not raw.startswith('file:') and path.is_relative_to(scratch))
        parts = path.relative_to(scratch).parts if valid else ()
        valid = (valid and len(parts) == 4 and parts[0] == current_test.split('.')[-1] and
            parts[1:3] == ('trial-0', 'state') and (parts[3] == 'authority.db' or
            re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db', parts[3]) is not None))
        if not valid:
            prohibited.append('sqlite3.connect:outside_exact_test_state')
            raise RuntimeError('SQLite connection outside exact retained trial state')
        if len(sqlite_connections) >= 1024: raise RuntimeError('SQLite connection inventory exceeds fixed bound')
        sqlite_connections.append({'testId': current_test, 'database': str(path)})
"""
        after=after.replace("    if event == 'exec':",hook+"    if event == 'exec':")
        after=after.replace('        def startTest(self, test):\n            executed_ids', '        def startTest(self, test):\n            global current_test\n            current_test = test.id()\n            executed_ids')
        after=after.replace('            super().startTest(test)\n', '            super().startTest(test)\n        def stopTest(self, test):\n            global current_test\n            super().stopTest(test)\n            current_test = None\n')
        after=after.replace("    finalize('actual-origins', origins_receipt)","    finalize('actual-origins', origins_receipt)\n    finalize('sqlite-connections', lambda: write('sqlite-connections.json', sqlite_connections))")
    ast.parse(after); (NEW/name).write_text(after)
    (NEW/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/name).relative_to(ROOT).as_posix(),tofile=(NEW/name).relative_to(ROOT).as_posix())))
(NEW/'README.md').write_text('# Isolated conflict52 harness\n\nRun39 unchanged pure transcript tests, nine new retained conflict simulations\nand four unchanged configured simulations from the [frozen candidate](../implementation01/README.md).\nSee [scope](SCOPE.md) and [exact selection](targets.json). Parent startup uses\npython3 -B; the child retains -I -S -B isolation.\n')
(NEW/'SCOPE.md').write_text('# Conflict52 execution scope\n\nOnly13 original private SQLite trial simulations and39 unchanged pure transcript\ntests execute. SQLite connections are restricted to the current selected runtime\ntest and its original trial-0/state authority/board databases. Network, subprocess\nlaunch, physical endpoints, MCU/emulator, inference, live services and acquired\ncontrollers remain prohibited. No adjacent project changes.\n\nKeep the original180-second deadline,16 MiB scratch,8192 inventory files,256 MiB\ninput acquisition,16 MiB file,4 MiB JSON and8 MiB log bounds. Keep all original\nraw scratch and failed evidence. Child audit hooks are cooperative guardrails,\nnot an OS sandbox or aggregate producer disk quota. No journal/provider/compiler\nbusiness logic, physical claims or qualification/effect ceilings change.\n\nThe new reader checks conflict/replay and composes retained histories. It does\nnot attest current source/configuration, run the full matrix or qualify a PAT.\nPrimary-agent review/release is required; helper agents are usage-limited.\n')
print(json.dumps(dict(sourceIndexSha256=source_pin,projectFiles=7067,frozenFiles=7070,tests=52)))
