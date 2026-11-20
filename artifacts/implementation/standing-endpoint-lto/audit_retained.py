"""Read retained build receipts and bytes; never import or execute candidate code."""
import hashlib
import json
import os
from pathlib import Path
import sys

if sys.flags.optimize != 0:
    raise RuntimeError('Retained-data audit requires assertions enabled')

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):
    assert not path.is_symlink() and path.stat().st_size < 8*1024**2
    def pairs(items):
        result = {}
        for key,value in items:
            assert key not in result
            result[key] = value
        return result
    return json.loads(path.read_bytes(),object_pairs_hook=pairs)


def snapshot():
    files = list((HERE/'build').rglob('*'))+list(HERE.glob('checks-*.json'))
    result = {}
    for path in sorted(files):
        assert not path.is_symlink()
        if path.is_file():
            result[str(path.relative_to(HERE))] = dict(bytes=path.stat().st_size,sha256=digest(path))
    return result


def main(destination_name='AUDIT.json'):
    assert destination_name in ('AUDIT.json','AUDIT-ATTEMPT-1.json')
    before = snapshot(); attempts = []; identities = set(); total_commands = 0; reports = []
    receipts = sorted(HERE.glob('checks-*.json'))
    assert 1 <= len(receipts) <= 10
    for path in receipts:
        report = read(path); folder = HERE/report['frozen_source_copy_root']
        sources = report['sources']
        assert len(sources) == (54 if report['attempt'] == 1 else 56)
        assert read(folder/'freeze-intent.json')['sources'] == sources
        assert report['source_hashes_after'] == report['copied_source_hashes_after'] == sources
        assert all(digest(folder/name) == value for name,value in sources.items())
        assert all(report[key] is True for key in ('source_preparation_completed','sources_unchanged',
            'copied_sources_unchanged','runtime_unchanged','installed_files_unchanged','tool_aliases_unchanged',
            'owner_empty','owner_closed','owned_groups_observed_absent'))
        assert not report['owner_cleanup_errors'] and not report['interrupts_pending_after_cleanup']
        assert all(item.get('members') == [] for item in report['final_group_audit'])
        assert report['installed_file_pins'] == report['installed_file_hashes_after']
        assert all(digest(Path(name)) == value for name,value in report['installed_file_pins'].items())
        assert report['tool_alias_pins'] == report['tool_aliases_after']
        for name,value in report['tool_alias_pins'].items():
            assert dict(linkname=os.readlink(name),resolved=str(Path(name).resolve(strict=True))) == value
        if report['attempt'] > 1:
            assert report['plugin_lookup_unchanged']
            assert report['plugin_lookup_after'] == report['plugin_lookup_expected']
            lookup = read(folder/'plugin-lookup.json')
            assert lookup['lookup'] == report['plugin_lookup_expected']
            assert lookup['prefixes'] == report['plugin_search_prefixes']
            assert lookup['mode'] == 'R_OK' and lookup['do_multi'] is False
            assert lookup['lookup']['resolved'] == lookup['expected_resolved']
            observed = dict(candidates=[],selected=None,resolved=None)
            for prefix in lookup['prefixes']:
                candidate = prefix+'liblto_plugin.so'; readable = os.access(candidate,os.R_OK)
                observed['candidates'].append(dict(path=candidate,readable=readable))
                if readable:
                    observed.update(selected=candidate,resolved=str(Path(candidate).resolve(strict=True)))
                    break
            assert observed == lookup['lookup']
        assert all(value == report['runtime_sha256'] for value in report['runtime_before'].values())
        assert all(value == report['runtime_sha256'] for value in report['runtime_after'].values())
        commands = report['commands']; reaped = []
        assert read(folder/'commands.json') == commands
        failures = []
        for command in commands:
            name = command['name']; result = read(folder/(name+'.result.json'))
            assert command == result
            intent = read(folder/(name+'.intent.json')); started = read(folder/(name+'.started.json'))
            assert all(result[key] == value for key,value in intent.items())
            assert started['pid'] == result['pid'] == result['pgid']
            assert result['direct_child_reaped'] and result['input_pins_stable']
            assert not result['group_members_after_cleanup'] and not result['cleanup_errors']
            assert not result['interrupts_pending_after_cleanup']
            assert result['inputs_before'] == result['inputs_after'] == dict(original=sources,frozen=sources)
            assert result['runtime_before'] == result['runtime_after']
            assert result['installed_files_before'] == result['installed_files_after']
            assert result['tool_aliases_before'] == result['tool_aliases_after'] == report['tool_alias_pins']
            if report['attempt'] > 1:
                assert result['plugin_lookup_before'] == result['plugin_lookup_after']
                if result['name'] in ('avr-version','avr-machine','avr-program-as','avr-program-ld',
                        'avr-program-cc1','avr-program-collect2','avr-program-lto1','avr-program-lto-wrapper',
                        'avr-program-search-dirs'):
                    assert result['plugin_lookup_before'] is None
                else:
                    assert result['plugin_lookup_before'] == report['plugin_lookup_expected']
            assert result['environment']['MAKE'] == '/usr/bin/make'
            assert not set(result['environment']) & {'MAKEFLAGS','MFLAGS','GNUMAKEFLAGS'}
            assert result['executable_after'] == dict(path=result['executable']['sha256'],opened=result['executable']['sha256'])
            assert digest(HERE/result['stdout']) == result['stdout_sha256']
            assert digest(HERE/result['stderr']) == result['stderr_sha256']
            members = result['owned_children_reaped']; reaped += members
            leader = [member for member in members if member['pid'] == result['pid']]
            assert len(leader) == 1 and leader[0]['exitCode'] == result['exit_code']
            assert all(leader[0][key] == started['identity'][key] for key in ('pid','startTicks','parent','group','session'))
            assert all(member['reaped'] is True for member in members)
            identities.update((member['pid'],member['startTicks']) for member in members)
            if result['passed']:
                assert result['exit_code'] == 0 and result['termination_reason'] is None
                assert not (HERE/result['stderr']).read_bytes()
            else:
                failures.append(dict(command=name,exitCode=result['exit_code'],stderrSha256=result['stderr_sha256']))
        assert report['owned_children_reaped'] == reaped
        total_commands += len(commands)
        if report['requested_checks_completed']:
            assert not failures
        assert report['stage'] == 'avr' and report['target_executed'] is False
        inventory = read(folder/'lto-artifacts.json')
        assert not inventory['final_stack_evidence_complete'] and not inventory['target_runtime_fit_demonstrated']
        assert len(inventory['files']) == report['lto_artifacts']['files']
        for row in inventory['files']:
            artifact = folder/row['path']
            assert artifact.is_relative_to(folder) and artifact.stat().st_size == row['bytes']
            assert digest(artifact) == row['sha256']
        if report['attempt'] == 1:
            assert not report['requested_checks_completed'] and len(commands) == 9 and not failures
            assert commands[-1]['name'] == 'avr-plugin-path'
            assert (folder/'avr-plugin-path.stdout').read_bytes() == b'liblto_plugin.so\n'
            assert report['error'] == 'RuntimeError: Outside compiler tree: '+str(ROOT/'liblto_plugin.so')
            assert not inventory['files'] and not (folder/'runtime.map').exists() and not (folder/'runtime.elf').exists()
        attempts.append(dict(receipt=path.name,sha256=digest(path),stage=report['stage'],attempt=report['attempt'],
                             completed=report['requested_checks_completed'],commands=len(commands),reaps=len(reaped),failures=failures))
        reports.append(report)
    current = read(HERE/'project-source-review.json')
    assert len(current['project_sha256']) == 36
    assert all(digest(HERE/'project'/name) == pin for name,pin in current['project_sha256'].items())
    assert digest(HERE/'project-source-diff.patch') == current['project_diff_sha256']
    matching = {stage: [report for report in reports if report['stage'] == stage and
        {name.removeprefix('project/'):pin for name,pin in report['sources'].items() if name.startswith('project/')} == current['project_sha256']]
        for stage in ('native','avr')}
    assert not matching['native'], 'No unchanged native test rerun was required in this lane'
    parent_native = read(ROOT/'artifacts/implementation/standing-endpoint-fit/checks-native.json')
    assert parent_native['requested_checks_completed']
    assert {name.removeprefix('project/'):pin for name,pin in parent_native['sources'].items()
            if name.startswith('project/')} == current['project_sha256']
    assert matching['avr'], 'Current sources have no retained AVR attempt'
    latest_avr = max(matching['avr'],key=lambda report:report['attempt'])
    if not latest_avr['requested_checks_completed']:
        assert latest_avr.get('error')
    original = read(HERE/'source-pins.json')['files']; assert len(original) == 36
    for row in original:
        assert digest(ROOT/row['source']) == digest(HERE/'originals'/row['copy']) == row['sha256']
    for pid,tick in identities:
        try:
            tail = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
        except FileNotFoundError:
            continue
        assert int(tail[19]) != tick, 'observed child identity remains, including zombie'
    public = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline = read(public); assert len(baseline['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in baseline['files'])
    assert snapshot() == before
    result = dict(passed=True,auditSourceSha256=digest(Path(__file__)),attempts=attempts,totalCommands=total_commands,
                  observedOwnedIdentitiesAbsent=len(identities),currentProjectFiles=36,originalCopies=36,publicInputsExact=244,
                  currentSourcesNativeCompletedInParent=True,nativeTestsRerun=False,currentSourcesAvrAttempt=latest_avr['attempt'],
                  currentSourcesAvrCompleted=latest_avr['requested_checks_completed'],
                  avrResourceArithmeticAudited=False,targetFitEstablished=False,
                  candidateCodeImported=False,checksRerun=False,targetExecuted=False,physicalIOQualified=False,
                  scope='Retained receipt/byte joins and process-identity absence. Unchanged-source native success belongs to the sealed parent. Audit pass does not mean LTO build success or validate final resource/stack/timing arithmetic.',retainedFiles=before)
    with (HERE/destination_name).open('x') as target:
        json.dump(result,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({key:value for key,value in result.items() if key!='retainedFiles'},sort_keys=True))


if __name__ == '__main__':
    assert len(sys.argv) <= 2
    main(sys.argv[1] if len(sys.argv) == 2 else 'AUDIT.json')
