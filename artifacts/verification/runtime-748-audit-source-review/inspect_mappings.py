"""Original stdlib receipt-field inspection; does not import or execute auditor."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
references=[]

def read(name):
    path=ROOT/name;body=path.read_bytes()
    references.append({'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    return json.loads(body)

def pair_map(rows):
    return {row['path']:(row['sha256'],row['bytes']) for row in rows}

public=read('artifacts/verification/io-provider-runtime-integration/proof.json')
recovery=read('artifacts/verification/io-status-read-timeout-resolution/proof.json')
failed=read('artifacts/verification/runtime-attempts/20261107T011441.670375Z-c1003207c4ba/receipt.json')
result_fields={'tests','failures','errors','inputs','passed','skips','expectedFailures','unexpectedSuccesses',
               'inputCaptureErrors','runnerErrors','inputsUnchanged','compilerStable','providerStable',
               'seconds','providerDigest','outputs'}
families={}
for label,proof in [('public',public),('recovery',recovery)]:
    attempts=[]
    for item in proof['attempts']:
        result=read(item['result']['path']);base=str(Path(item['result']['path']).parent)
        before=read(base+'/inputs-before.json');after=read(base+'/inputs-after.json')
        cb=read(base+'/compiler-before.json');ca=read(base+'/compiler-after.json')
        pb=read(base+'/provider-before.json');pa=read(base+'/provider-after.json')
        attempts.append({'counts':[result[k] for k in ('tests','failures','errors','inputs','passed')],
            'missingRequiredResultFields':sorted(result_fields-set(result)),
            'itemResultScalarsEqual':all(item[k]==result[k] for k in ('tests','failures','errors','skips','inputs','seconds','passed','providerDigest')),
            'beforeRows':len(before),'afterRows':len(after),'distinctBeforePaths':len(pair_map(before)),
            'sourceMapsEqual':pair_map(before)==pair_map(after),'compilerPairEqual':cb==ca,
            'compilerImportMatchesCurrent':cb['import_matches_current'],
            'providerPairEqualExpected':pb==pa=={'digest':result['providerDigest']}})
    families[label]=attempts
public_last=Path(public['attempts'][-1]['result']['path']).parent
public_map=pair_map(read(str(public_last/'inputs-before.json')))
public_core={p:v for p,v in public_map.items() if p not in {
    'artifacts/verification/io-provider-runtime-integration/run.py',
    'artifacts/verification/io-provider-runtime-integration/run_transports.py'}}
recovery_last=Path(recovery['attempts'][-1]['result']['path']).parent
recovery_map=pair_map(read(str(recovery_last/'inputs-before.json')))
recovery_core={p:v for p,v in recovery_map.items() if p!='artifacts/verification/io-status-read-timeout-resolution/run.py'}
current=read('artifacts/verification/local-runtime-current.json')
# Inspect the already captured current attempt inputs. No terminal pass inferred.
current_tree=ROOT/current['attempt_dir']/'inputs-before'
current_map={str(p.relative_to(current_tree)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_size)
             for p in current_tree.rglob('*') if p.is_file()}
public_report=read(public['finalTransportReport']['path'])
recovery_report=read(recovery['finalTransportReport']['path'])
controlled=recovery_report['cases']['test_io_transport.IoTransportTests.test_status_polling_recovers_only_read_timeouts_within_original_deadline']['results']['controlledPolling']
manifest_maps={};lifecycles=[]
for number in ('03','04','05'):
    prefix='artifacts/implementation/io-lifecycle-settlement/review-inputs/'+number
    manifest=read(prefix+'/manifest.json');prep=read(prefix+'/source-preparation.json')
    manifest_maps[number]={r['path']:r['sha256'] for r in manifest['files']}
    lifecycles.append({'snapshot':number,'manifestRows':len(manifest['files']),
        'incorrectHmsPrefixCount':sum(p.startswith('hms/') for p in manifest_maps[number]),
        'correctProjectHmsPrefixCount':sum(p.startswith('project/hms/') for p in manifest_maps[number]),
        'unexecutedFields':{k:prep[k] for k in ('projectImported','testsExecuted','runtimeExecuted','executionReleased')}})
reviews=[]
for number in ('04','05'):
    r=read('artifacts/verification/io-lifecycle-harness-remediation-review/'+number+'/review.json')
    reviews.append({'snapshot':r['snapshot'],'status':r['status'],'findingStatuses':[f['status'] for f in r['findings']],
        'hmsUnchanged':r['staticChecks']['hmsFilesUnchangedFrom03'],
        'manifestHash':r['manifestSha256' if number=='04' else 'sourceManifestSha256'],
        'executionFields':{k:r[k] for k in ('reviewerProjectImports','reviewerTests','reviewerRuntimeOrSubprocessExecution','reviewerLiveEdits')}})
baseline_hms={p:v for p,v in manifest_maps['03'].items() if p.startswith('project/hms/')}
values={'profile':'hms.original-receipt-mapping-inspection/1','method':'Only stdlib JSON/bytes inspection; no auditor/checker/project import or execution',
    'attemptFamilies':families,'historicalFocused4CoreCount':len(public_core),'historicalFocused4EqualsFailed747FilesBefore':public_core==pair_map(failed['files_before']),
    'failed747BeforeAfterMapsEqual':pair_map(failed['files_before'])==pair_map(failed['files_after']),
    'failed747Counts':[failed[k] for k in ('tests','failures','errors','skipped')],
    'newFocused5CoreCount':len(recovery_core),'activeCurrentAttempt':current['attempt_id'],'activeCurrentStatusAtRead':current['status'],
    'currentCapturedBeforeCount':len(current_map),'newFocused5EqualsCurrentCapturedBefore':recovery_core==current_map,
    'changedCorePathsFromHistorical4':sorted(p for p in public_core if public_core[p]!=recovery_core.get(p)),
    'historical4CaseCount':len(public_report['cases']),'historical4AllCasesPassed':all(c['passed'] is True for c in public_report['cases'].values()),
    'historical4ObserverCount':sum(len(c['observerReads']) for c in public_report['cases'].values()),
    'new5CaseCount':len(recovery_report['cases']),'new5AllCasesPassed':all(c['passed'] is True for c in recovery_report['cases'].values()),
    'controlledCaseCount':len(controlled['cases']),'controlledCasesEqualProof':controlled['cases']==recovery['controlledCases'],
    'lifecycleSnapshots':lifecycles,'lifecycleHms03Equals04Equals05':all({p:v for p,v in manifest_maps[n].items() if p.startswith('project/hms/')}==baseline_hms for n in ('04','05')),
    'lifecycleReviews':reviews,'scopeLimit':'Current full748 terminal receipt was not available at design start; captured before inputs are not a passing result. Auditor was not run.'}
(OUT/'mapping-values.json').write_text(json.dumps(values,indent=2,sort_keys=True)+'\n')
# Preserve selected receipt documents only, not another full test-source archive.
seen={}
for row in references:seen[row['path']]=row
for name,row in seen.items():
    dest=OUT/'receipts'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
(OUT/'references.json').write_text(json.dumps(list(seen.values()),indent=2,sort_keys=True)+'\n')
print(json.dumps({k:values[k] for k in ['historicalFocused4CoreCount','historicalFocused4EqualsFailed747FilesBefore','newFocused5CoreCount','newFocused5EqualsCurrentCapturedBefore','changedCorePathsFromHistorical4','lifecycleHms03Equals04Equals05','activeCurrentStatusAtRead']}))
