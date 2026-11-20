"""Data-only cross-check of six acquired original clock histories."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tables(cp,docs):
    return {t['table']:[dict(zip(docs[p['path']]['value']['columns'],[v['value'] for v in row]))
            for p in t['pages'] for row in docs[p['path']]['value']['rows']] for t in cp['tables']}
cases=[]
for path in sorted((BASE/'attempt01/scratch').glob('*/engine-0.json')):
    manifest=read(path);checked=manifest['independentClockInspection'];scenario=checked['scenario']
    assert checked['exactClockControlScheduleChecked'] and checked['qualificationPassed'] is checked['independentOutcomeChecked'] is checked['expectedResponseVerified'] is False
    streams=[]
    for folder,refs in [('records',manifest['records']),('configuration',manifest['configuration']['records'])]:
        docs={}
        for ref in refs:
            p=path.parent/'trial-0'/folder/ref['path'];assert p.stat().st_size==ref['bytes'] and sha(p)==ref['sha256'];docs[ref['path']]=read(p)
        streams.append(docs)
    docs,cd=streams;snapshots=[]
    for pair in manifest['configuration']['snapshots']:
        cp=docs[pair['checkpoint']['path']]['value'];cfg=cd[pair['configuration']['path']]['value']
        snapshots.append((cp,tables(cp,docs),tables(cfg,cd)))
    errors=[];reopens=[]
    for i,(cp,t,c) in enumerate(snapshots):
        if cp['label']=='drive:adapters:after_error':
            prior,old,oldcfg=snapshots[i-1];assert prior['label']=='drive:adapters:before' and prior['phase']==cp['phase']
            assert old==t and oldcfg==c and len(t['operations'])==1
            assert t['operations'][0]['state']=='running' and t['claims'] and t['io_owners']
            receipt=read_document=t['io_receipts'][0]['document'];receipt=json.loads(receipt)
            assert receipt['state']=='pending' and receipt['sequence']==1
            assert dict((r['key'],r['value']) for r in t['meta'])['last_clock']=='1000000'
            errors.append(dict(phase=cp['phase'],wallMs=cp['wallMs'],monotonicMs=cp['monotonicMs'],all44TablesUnchanged=True,claims=len(t['claims'])))
        if cp['label']=='after_reopen':
            prior,old,oldcfg=snapshots[i-1];assert prior['label']=='before_reopen'
            assert t['operations'][0]['state']=='outcome_unknown' and t['claims']==old['claims'] and not t['io_owners']
            assert json.loads(t['io_receipts'][0]['document'])['result']['reason']=='board_owner_reopened'
            assert t['pr_procedures'][0]['request']==old['pr_procedures'][0]['request']
            assert t['resource_floors']==old['resource_floors'] and t['io_dispatch_links']==old['io_dispatch_links']
            assert t['replay_keys']==old['replay_keys'] and t['pr_keys']==old['pr_keys']
            reopens.append(dict(phase=cp['phase'],newClockEpoch=cp['clockEpoch'],claimsRetainedUntilReconciliation=True))
    cp,final,_=snapshots[-1];assert cp['label']=='test_final'
    sums=tuple(sum(r[k] for r in final['io_effects']) for k in ('activations','completed','canceled'))
    assert sums==((0,0,0) if scenario=='start_run_equal' else (1,0,1))
    assert len(final['operations'])==1 and not final['claims'] and not final['io_owners']
    assert len(errors)==(0 if scenario=='start_run_equal' else 1 if scenario=='wall_clock_regression' else 2)
    assert len(reopens)==(0 if scenario=='start_run_equal' else 1)
    if scenario=='start_run_equal':
        receipt=json.loads(final['io_receipts'][0]['document']);link=json.loads(final['io_dispatch_links'][0]['document'])
        assert receipt['state']=='rejected_before_start' and receipt['result']['reason']=='duration_budget_excluded'
        assert link['budgetOriginMonoMs']==1000000 and cp['monotonicMs']==1000099 and not final['io_fences']
    cases.append(dict(manifest=path.relative_to(BASE).as_posix(),manifestSha256=sha(path),scenario=scenario,
        activations=sums[0],completedCycles=sums[1],canceledActivations=sums[2],ticks=checked['schedulerTicks'],
        checkpoints=len(snapshots),executionRecords=len(docs),configurationRecords=len(cd),failedClockPhases=errors,newEpochReopens=reopens))
assert len(cases)==6
totals={k:sum(c[k] for c in cases) for k in ('activations','completedCycles','canceledActivations','ticks','checkpoints','executionRecords','configurationRecords')}
assert totals==dict(activations=4,completedCycles=0,canceledActivations=4,ticks=28,checkpoints=116,executionRecords=664,configurationRecords=270)
result=dict(scope='Primary-agent acquired-data cross-check; no project execution or full independent semantic/outcome proof.',
    cases=cases,totals=totals,allClockFailedPhasesUnchanged=True,qualificationPassed=False,independentClockOutcomeChecked=False,
    physicalMeasurementChecked=False,independentAgentReview=False)
with (BASE/'data-audit.json').open('x')as f:f.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(totals))
