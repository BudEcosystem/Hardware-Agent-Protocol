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


def main():
    before = snapshot(); attempts = []; identities = set(); total_commands = 0; reports = []
    receipts = sorted(HERE.glob('checks-*.json'))
    assert [path.name for path in receipts] == ['checks-avr.json','checks-native.json']
    assert digest(HERE/'checks-native.json') == '13a655a2aeb9edf4d605f405b24999a8e1eafdbad2ce7cc01831df8856702f04'
    assert digest(HERE/'checks-avr.json') == 'c48444ae4c8eae3c3bd71ddee851b6c95e030869dc7a8de782e78391cff7f36a'
    for path in receipts:
        report = read(path); folder = HERE/report['frozen_source_copy_root']
        assert report['attempt'] == 1 and report['stage'] in ('native','avr')
        assert folder == HERE/'build'/report['stage']
        sources = report['sources']
        assert len(sources) == 65
        assert read(folder/'freeze-intent.json')['sources'] == sources
        assert report['source_hashes_after'] == report['copied_source_hashes_after'] == sources
        assert all(digest(folder/name) == digest(HERE/name) == value for name,value in sources.items())
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
        if report['stage'] == 'avr':
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
        else:
            assert report['plugin_lookup_unchanged'] and not report['plugin_search_prefixes']
            assert report['plugin_lookup_after'] is report['plugin_lookup_expected'] is None
            assert not report['tool_alias_pins']
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
            assert result['plugin_lookup_before'] == result['plugin_lookup_after']
            if report['stage'] == 'avr':
                if result['name'] in ('avr-version','avr-machine','avr-program-as','avr-program-ld',
                        'avr-program-cc1','avr-program-collect2','avr-program-lto1','avr-program-lto-wrapper',
                        'avr-program-search-dirs'):
                    assert result['plugin_lookup_before'] is None
                else:
                    assert result['plugin_lookup_before'] == report['plugin_lookup_expected']
                assert result['environment']['MAKE'] == '/usr/bin/make'
                assert result['environment']['TMPDIR'] == str(folder/'compiler-tmp')
            else:
                assert result['plugin_lookup_before'] is None
                assert not set(result['environment']) & {'MAKE','TMPDIR'}
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
        assert report['target_executed'] is False
        if report['stage'] == 'avr':
            assert not report['requested_checks_completed'] and len(commands) == len(reaped) == 23
            assert len(failures) == 1 and failures[0]['command'] == 'avr-link' and failures[0]['exitCode'] == 1
            assert commands[-1]['name'] == 'avr-link' and all(command['passed'] for command in commands[:-1])
            assert sum(command['name'].startswith('avr-compile-') for command in commands) == 12
            assert b"overflowed by 9042 bytes" in (folder/'avr-link.stderr').read_bytes()
            assert not (folder/'runtime.elf').exists()
            inventory = read(folder/'lto-artifacts.json')
            assert not inventory['final_stack_evidence_complete'] and not inventory['target_runtime_fit_demonstrated']
            assert len(inventory['files']) == report['lto_artifacts']['files']
            assert inventory['possible_backend_stack_files'] == report['lto_artifacts']['possible_backend_stack_files']
            for row in inventory['files']:
                artifact = folder/row['path']
                assert artifact.is_relative_to(folder) and artifact.stat().st_size == row['bytes']
                assert digest(artifact) == row['sha256']
            stack = read(folder/'pre-lto-stack-records.json')
            assert stack['scope'] == 'Conventional fat-object frames; not final LTO stack evidence'
            assert all(row['phase'] == 'pre-LTO fat-object compilation' for row in stack['records'])
        else:
            assert report['requested_checks_completed'] and len(commands) == 14
            native = report['native']; original = native['original']
            assert original == read(folder/'original-native.stdout')
            assert original['passed'] and original['pipe_smoke'] == 'passed'
            assert original['native_tests']['cases'] == 26 and original['native_tests']['assertions'] == 2548
            assert original['native_tests']['malformed_inputs'] == 20000
            original_receipt = read(folder/'project'/original['receipt'])
            assert original_receipt['passed'] and original_receipt['native_tests'] == original['native_tests']
            assert original_receipt['compiler']['path'] == native['compiler_path']
            assert original_receipt['compiler']['sha256'] == native['compiler_sha256']
            assert digest(folder/'project'/original['pipe_binary']) == original['pipe_sha256']
            for row in original_receipt['outputs']:
                assert digest(folder/'project'/row['path']) == row['sha256']
            assert native['plain_sanitized_reports_agree'] and native['standing_observed_assertions'] == 766
            assert native['standing']['plain'] == native['standing']['asan']
            assert native['integration']['plain'] == native['integration']['asan']
            for mode in ('plain','asan'):
                standing = native['standing'][mode]; integration = native['integration'][mode]
                assert standing == read(folder/('standing-probe-'+mode+'.stdout'))
                assert standing == dict(assertions=766,cases=14,physical_qualification=False)
                assert integration == read(folder/('probe-'+mode+'.stdout'))
                assert integration == dict(assertions=143471,cases=11,interruptSnapshots=256,
                                           status='passed',targetExecuted=False,wireOracleSteps=20000)
            assert native['source_coverage'] == read(folder/'native-source-coverage.json')
            assert native['source_coverage'] == dict(baseline_case_bodies_verified=13,
                baseline_observed_assertions=673,standing_cases_required=14,
                coverage_profile_sha256=digest(folder/'native-coverage.json'))
        attempts.append(dict(receipt=path.name,sha256=digest(path),stage=report['stage'],attempt=report['attempt'],
                             completed=report['requested_checks_completed'],commands=len(commands),reaps=len(reaped),failures=failures))
        reports.append(report)
    assert total_commands == len(identities) == 37
    current = read(HERE/'project-source-review.json')
    assert len(current['project_sha256']) == 36
    assert all(digest(HERE/'project'/name) == pin for name,pin in current['project_sha256'].items())
    assert digest(HERE/'project-source-review.json') == 'e37adaad24506bb39f975b8d942791aa39c844e411422aac2979b509deb724f9'
    assert digest(HERE/'project.diff') == current['reviews_and_inputs']['project.diff']
    assert digest(HERE/'run_checks.py') == current['runner_sha256']
    assert digest(HERE/'runner-diff.patch') == current['runner_diff_sha256']
    assert all(digest(HERE/name) == value for name,value in current['reviews_and_inputs'].items())
    matching = {stage: [report for report in reports if report['stage'] == stage and
        {name.removeprefix('project/'):pin for name,pin in report['sources'].items() if name.startswith('project/')} == current['project_sha256']]
        for stage in ('native','avr')}
    assert len(matching['native']) == 1 and matching['native'][0]['requested_checks_completed']
    assert matching['avr'], 'Current sources have no retained AVR attempt'
    latest_avr = max(matching['avr'],key=lambda report:report['attempt'])
    if not latest_avr['requested_checks_completed']:
        assert latest_avr.get('error')
    original = read(HERE/'source-pins.json')['baseline_project']; assert len(original) == 36
    for name,value in original.items():
        assert digest(HERE/'originals/project'/name) == value
        assert digest(ROOT/'artifacts/implementation/standing-endpoint-lto/project'/name) == value
    history = read(HERE/'history/source-proposal/index.json')
    assert history['file_count'] == len(history['files']) == 93
    for row in history['files']:
        path = HERE/'history/source-proposal'/row['path']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    coverage = read(HERE/'native-coverage.json')
    baseline = (HERE/coverage['baseline_source']).read_bytes()
    active = (HERE/coverage['current_source']).read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == coverage['baseline_sha256']
    assert hashlib.sha256(active).hexdigest() == coverage['current_sha256']
    assert len(coverage['unchanged_case_bodies']) == 13
    for row in coverage['unchanged_case_bodies']:
        a,b = row['baseline_span']; c,d = row['current_span']
        assert baseline[a:b] == active[c:d]
        assert hashlib.sha256(baseline[a:b]).hexdigest() == row['sha256']
    retained = coverage['retained_result']
    assert digest(ROOT/retained['path']) == retained['sha256']
    assert read(ROOT/retained['path'])['native'] == retained['native']
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
                  currentSourcesNativeCompleted=True,standingCasesObserved=14,standingAssertionsObserved=766,
                  oldStandingCaseBodiesExact=13,sourceProposalHistoryFilesExact=93,currentSourcesAvrAttempt=latest_avr['attempt'],
                  currentSourcesAvrCompleted=latest_avr['requested_checks_completed'],
                  avrResourceArithmeticAudited=False,targetFitEstablished=False,
                  candidateCodeImported=False,checksRerun=False,targetExecuted=False,physicalIOQualified=False,
                  scope='Retained receipt/byte joins and process-identity absence. Current-source native success and AVR outcome are explicit; audit pass does not mean AVR success or validate final resource/stack/timing arithmetic.',retainedFiles=before)
    with (HERE/'AUDIT.json').open('x') as target:
        json.dump(result,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({key:value for key,value in result.items() if key!='retainedFiles'},sort_keys=True))


if __name__ == '__main__':
    assert len(sys.argv) == 1
    main()
