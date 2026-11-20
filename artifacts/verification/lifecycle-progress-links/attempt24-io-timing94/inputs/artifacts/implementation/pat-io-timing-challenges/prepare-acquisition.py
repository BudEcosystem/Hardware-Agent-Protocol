"""Prepare corrected-attempt acquisition from the reviewed initial collector."""
import ast
import difflib
import json
from pathlib import Path

BASE=Path('artifacts/implementation/pat-io-timing-challenges');OLD=BASE/'results/attempts01-02/acquire.py';OUT=BASE/'results/attempts03-05'
OUT.mkdir(exist_ok=False);before=OLD.read_text();after=before.replace('both failed timing-reader attempts','the three corrected timing attempts')
after=after.replace("OUT=BASE/'results/attempts01-02'","OUT=BASE/'results/attempts03-05'")
after=after.replace("BASE/'implementation01','adb63bce663e249d06b1c46bec3d04fed6d1111e43796dd56c9567211bcbd381'","BASE/'implementation02','6a7531015ffe1e5a758e7cbe27d94f54a6a9134e8e423d14e40b45154a7e46a0'")
start=after.index('for number,harness,name,count,pin,target in [');end=after.index('    H=BASE/harness;',start)
after=after[:start]+"""for number,harness,name,count,pin,target in [
    ('03','harness03','attempt03-gpio9',9,'53d8141865899203d4562f52ad2f299b424764cf9d9394c8889dc6cc2238a729','6bae4b76ebe7c7572737df7151c72e53e0d19723f0861ee95fbd92a9da45cd04'),
    ('04','harness04','attempt04-pwm8',8,'5d7de5288ec2703bbf170f14c6114edabaa56936f92bd8c23abf3dc10bab9696','a6e04e9ee69b5749b229e8614136e5be2cf950d0e70ee67dc477a07f4d78c545'),
    ('05','harness05','attempt05-regression77',77,'fa2f9fee9301bc59dc4d705cdc240a912e8ec0bcdb96d18b6bc403aa03dd9194','498caf84cfe1b12730c9a4107a8cd69643b5a8d64c67c7620009c5e1f6a36e4c')]:
"""+after[end:]
after=after.replace("result['status']=='failed' and not result['currentPass'] and result['exitCode']==1", "result['status']=='passed' and result['currentPass'] and result['exitCode']==0")
after=after.replace('failures=0,errors=2,','failures=0,errors=0,')
after=after.replace('    for test in targets:\n','    for test in ([] if count==77 else targets):\n')
start=after.index("        failed=method in {");end=after.index("        dbs=list",start)
after=after[:start]+"""        assert 'inspectionError' not in manifest
        checked=manifest['independentTimingInspection'];assert checked['expectedResponseVerified'] and checked['independentOutcomeChecked']
        assert not checked['qualificationPassed'] and not checked['requiredMatrixCoverageChecked']
        assert requested['expectedSetup']=={docs[r['path']]['kind']:docs[r['path']]['value'] for r in manifest['records'][:4]}
        assert len((d/'trial-manifest.json').read_bytes())<=65536
        assert manifest['configuration']['combinedRecords']+1<=4096
        assert manifest['configuration']['combinedBytes']+(d/'trial-manifest.json').stat().st_size<=16*1024*1024
        if count==9 and method=='test_timing_late_parent_reporting':assert manifest['rehashedCaseRefusals']==11
        if count==9 and method=='test_timing_latest_start_equal':assert manifest['rehashedExpiryRefusals']==4
"""+after[end:]
after=after.replace('inspectionFailed=failed,','inspectionFailed=False,outcome=checked[\'trial\'][\'outcome\'],')
after=after.replace("    assert len(cases)==8 and sum(c['inspectionFailed']for c in cases)==2", "    assert len(cases)==(0 if count==77 else 8) and not any(c['inspectionFailed']for c in cases)\n    if count==77:assert raw_rows==[]")
after=after.replace('and len(connections)==16','and len(connections)==(0 if count==77 else 16)')
after=after.replace("log.endswith('FAILED (errors=2)\\n')", "log.endswith('\\nOK\\n')")
after=after.replace("status='failed',counts=result", "status='passed',counts=result")
after=after.replace('Two failed verifier attempts: runtime captures completed, four expiry inspections refused by configuration cause handling.',
    'Corrected17 new methods plus77 unchanged configuration/refusal methods across three successful bounded invocations; all16 timing responses verified.')
after=after.replace("with(OUT/'proof.json')", "assert sum(s['counts']['testsRun']for s in summaries)==94\nassert sum(len(s['cases'])for s in summaries)==16\nwith(OUT/'proof.json')")
ast.parse(after);(OUT/'acquire.py').write_text(after)
(OUT/'acquire.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(OLD),tofile=str(OUT/'acquire.py'))))
print(json.dumps(dict(prepared=str(OUT/'acquire.py'),projectCodeExecuted=False)))
