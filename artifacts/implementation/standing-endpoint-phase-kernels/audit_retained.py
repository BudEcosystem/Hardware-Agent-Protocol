"""Read retained build receipts and bytes; never import or execute candidate code."""
import hashlib
import json
import os
import re
from pathlib import Path
import sys

if sys.flags.optimize != 0:
    raise RuntimeError('Retained-data audit requires assertions enabled')

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT_AUDIT_SHA256 = '892c961d48d24e097c34fb11d3b18555574712740421c07374d0b4a9822262ff'
CURRENT_REVIEW_SHA256 = '8a2b1fafb71d84ae49fc83cf6edcf07520613f7d46fbe2d46e52958d64a3f7d5'
NATIVE_RECEIPT_SHA256 = '44a4b3ccd0c9ae75bc6e3d578cc15f16e38c4b1cec7007a2a6b190bbd7e0383f'
AVR_RECEIPT_SHA256 = 'b8a911b2a15ea4e8aa41791f80bb0d5193b2a1fa5ccbe7f418169a9b3a92d81f'
AVR_MAP_SHA256 = '12336960e81dbb8d6dd998ea2d061fabb5db1df8a509a1bd8d9a50585610328c'
TRACE_SHA256 = '6eda3f924f18792751bd0ff643d1c53cb7bc3684c94a828de5c4f91572f0adc2'


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


def contained(folder, name):
    relative = Path(name)
    assert not relative.is_absolute() and relative.parts and '..' not in relative.parts
    path = folder/relative
    assert path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink()
    return path


def verify_index(folder, expected):
    assert digest(folder/'index.json') == expected
    index = read(folder/'index.json'); rows = index['files']
    assert len({row['path'] for row in rows}) == len(rows)
    if 'fileCount' in index: assert index['fileCount'] == len(rows)
    actual = {str(path.relative_to(folder)) for path in folder.rglob('*')
              if path.is_file() and path != folder/'index.json'}
    assert actual == {row['path'] for row in rows}
    for row in rows:
        path = contained(folder,row['path'])
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    return len(rows)


def fixed_sources():
    fixed = ['run_checks.py','PLAN.md','WIRE.md','wire-vectors.json','source-pins.json',
        'README.md','REVIEW.md','project-source-review.json','project.diff',
        'runner-owner-pins.json','RUNNER-REVIEW.md','toolchain-pins.json','retention.json','PROFILE.md',
        'PLUGIN-LOOKUP-REVIEW.md','plugin-lookup-source-pins.json',
        'CONTROLS.md','SOURCE-COVERAGE.md','INDEPENDENT-REVIEW.md','native-coverage.json',
        'runner-input-pins.json','runner-diff.patch','runner-baseline.py',
        'baseline-pins.json','proposal-index.json','CORE-DRAFT01.md','CONTROLS-DRAFT01.md']
    fixed += [str(path.relative_to(HERE)) for path in (HERE/'project').rglob('*') if path.is_file()
              and 'artifacts' not in path.relative_to(HERE/'project').parts and '__pycache__' not in path.parts]
    for prefix in ('originals','history'):
        fixed += [str(path.relative_to(HERE)) for path in (HERE/prefix).rglob('*') if path.is_file()]
    fixed += [row['target'] for row in read(HERE/'runner-owner-pins.json')['files']]
    assert len(fixed) == len(set(fixed))
    return {name:digest(contained(HERE,name)) for name in fixed}


def native_plan():
    names = ['native-version']+['native-program-'+name for name in ('cc1','as','ld','collect2')]+['original-native']
    for mode in ('plain','asan'):
        names += [prefix+'-'+mode for prefix in ('compile','probe','standing-compile','standing-probe')]
        for backend in ('byte','fallback'):
            names += ['kernel-'+phase+'-'+backend+'-'+mode for phase in ('compile','probe')]
        for domain in ('baseline','candidate','fallback'):
            names += ['equivalence-'+phase+'-'+domain+'-'+mode for phase in ('compile','probe')]
    assert len(names) == 34
    return names


AVR_UNITS = ('endpoint','kernel','link','standing','frame','uart','usart','clock','eeprom','boot','runtime',
             'standing-fixture','target')
AVR_QUERIES = ('avr-version','avr-machine','avr-program-as','avr-program-ld','avr-program-cc1',
    'avr-program-collect2','avr-program-lto1','avr-program-lto-wrapper','avr-program-search-dirs','avr-builtin-specs')
AVR_PLAN = list(AVR_QUERIES)+['avr-compile-'+unit for unit in AVR_UNITS]+[
    'avr-link','avr-sections','avr-symbols','avr-disassembly','avr-undefined']


def check_native(report, folder):
    native = report['native']; original = native['original']
    assert original == read(folder/'original-native.stdout')
    assert original['passed'] and original['pipe_smoke'] == 'passed'
    assert original['native_tests']['cases'] == 26 and original['native_tests']['assertions'] == 2548
    assert original['native_tests']['malformed_inputs'] == 20000
    original_receipt = read(contained(folder/'project',original['receipt']))
    assert original_receipt['passed'] and original_receipt['native_tests'] == original['native_tests']
    assert original_receipt['compiler']['path'] == native['compiler_path']
    assert original_receipt['compiler']['sha256'] == native['compiler_sha256']
    assert digest(contained(folder/'project',original['pipe_binary'])) == original['pipe_sha256']
    for row in original_receipt['outputs']:
        assert digest(contained(folder/'project',row['path'])) == row['sha256']
    assert native['plain_sanitized_reports_agree'] and native['standing_observed_assertions'] == 766
    assert native['selected_candidate_backend'] == 1 and native['scalar_fallback_controls'] is True
    assert '-DHMS_EP_BYTE_BACKEND=1' in original_receipt['plain_flags']
    assert '-DHMS_EP_BYTE_BACKEND=1' in original_receipt['sanitized_flags']
    for key in ('standing','integration','kernel','equivalence'):
        assert native[key]['plain'] == native[key]['asan']
    traces = []; observed = {}
    for mode in ('plain','asan'):
        standing = native['standing'][mode]; integration = native['integration'][mode]
        assert standing == read(folder/('standing-probe-'+mode+'.stdout'))
        assert standing == dict(assertions=766,cases=14,physical_qualification=False)
        assert integration == read(folder/('probe-'+mode+'.stdout'))
        assert integration == dict(assertions=143471,cases=11,interruptSnapshots=256,
                                   status='passed',targetExecuted=False,wireOracleSteps=20000)
        kernels = native['kernel'][mode]
        for label,backend in (('byte',1),('fallback',0)):
            kernel = kernels[label]
            assert kernel == read(folder/('kernel-probe-'+label+'-'+mode+'.stdout'))
            assert kernel['cases'] == 6 and kernel['old_cases'] == 3 and kernel['backend'] == backend
            assert type(kernel['assertions']) is int and kernel['assertions'] == 86889
            assert kernel['physical_qualification'] is False
        assert {k:v for k,v in kernels['byte'].items() if k!='backend'} == {
            k:v for k,v in kernels['fallback'].items() if k!='backend'}
        baseline = (folder/('equivalence-probe-baseline-'+mode+'.stdout')).read_bytes()
        candidate = (folder/('equivalence-probe-candidate-'+mode+'.stdout')).read_bytes()
        fallback = (folder/('equivalence-probe-fallback-'+mode+'.stdout')).read_bytes()
        assert baseline == candidate == fallback and candidate.endswith(b'\n')
        summary = json.loads(candidate.splitlines()[-1]); eq = native['equivalence'][mode]
        assert summary == eq['summary'] and summary['equivalence_cases'] == 20 and summary['old_cases'] == 14
        assert type(summary['added_assertions']) is int and summary['added_assertions'] == 851
        assert summary['assertions'] == 766+summary['added_assertions']
        assert type(summary['trace_records']) is int and summary['trace_records'] == 1177
        assert summary['physical_qualification'] is False
        records = [line.split(b' ',3)[1] for line in candidate.splitlines() if line.startswith(b'S ')]
        assert records == [str(index).encode('ascii') for index in range(1,summary['trace_records']+1)]
        assert eq['baseline_matches_candidate'] and eq['baseline_matches_fallback'] and eq['raw_outputs_retained']
        assert hashlib.sha256(candidate).hexdigest() == eq['complete_trace_sha256'] == TRACE_SHA256
        traces.append(candidate)
        observed = dict(standingCases=14,standingAssertions=766,kernelCases=6,kernelAssertions=kernel['assertions'],kernelBackends=[1,0],
            equivalenceCases=20,equivalenceAssertions=summary['assertions'],addedAssertions=summary['added_assertions'],
            traceRecords=summary['trace_records'],completeTraceSha256=eq['complete_trace_sha256'],
            differentialDomains=['exact-parent-scalar','candidate-byte','candidate-scalar-fallback'],sixTracesEqual=True)
    assert traces[0] == traces[1]
    assert native['source_coverage'] == read(folder/'native-source-coverage.json')
    assert native['source_coverage'] == dict(baseline_case_bodies_verified=14,
        baseline_observed_assertions=766,standing_cases_required=14,other_original_functions_verified=5,
        coverage_profile_sha256=digest(folder/'native-coverage.json'))
    return observed


def check_compile_selection(command, folder):
    name=command['name']; argv=command['argv']
    defines=[arg for arg in argv if arg.startswith('-DHMS_EP_BYTE_BACKEND=')]
    if name.startswith(('avr-compile-','standing-compile-')) or name in ('avr-link','compile-plain','compile-asan'):
        assert defines == ['-DHMS_EP_BYTE_BACKEND=1']
    elif name.startswith('kernel-compile-'):
        backend='1' if name.startswith('kernel-compile-byte-') else '0'
        assert defines == ['-DHMS_EP_BYTE_BACKEND='+backend]
    elif name.startswith('equivalence-compile-'):
        domain=name.removeprefix('equivalence-compile-').rsplit('-',1)[0]
        assert domain in ('baseline','candidate','fallback')
        backend='1' if domain=='candidate' else '0'
        assert defines == ['-DHMS_EP_BYTE_BACKEND='+backend]
        assert '-DHMS_EQ_EXPECTED_BACKEND='+backend in argv
        assert ('-DHMS_EQ_BASELINE' in argv) == (domain=='baseline')
        prefix=folder/'originals/project' if domain=='baseline' else folder/'project'
        assert str(prefix/'protocol/endpoint/endpoint_kernel.c') in argv
        assert str(folder/'project/tests/phase_access.c') in argv
        assert not any(arg.endswith('/protocol/endpoint/standing.c') or arg=='protocol/endpoint/standing.c' for arg in argv)


def check_avr(report, folder):
    assert digest(folder/'runtime.map') == AVR_MAP_SHA256
    inventory = read(folder/'lto-artifacts.json')
    assert not inventory['final_stack_evidence_complete'] and not inventory['target_runtime_fit_demonstrated']
    assert len(inventory['files']) == report['lto_artifacts']['files'] == 58
    assert inventory['possible_backend_stack_files'] == report['lto_artifacts']['possible_backend_stack_files']
    seen = set()
    for row in inventory['files']:
        artifact = contained(folder,row['path']); assert row['path'] not in seen; seen.add(row['path'])
        assert artifact.stat().st_size == row['bytes'] and digest(artifact) == row['sha256']
    expected_artifacts = set(); backend = []; pre_su = {unit+'.su' for unit in AVR_UNITS}
    for artifact in sorted(folder.rglob('*')):
        if not artifact.is_file() or artifact.is_symlink(): continue
        relative = artifact.relative_to(folder); name = artifact.name
        if relative.parts[0] in ('project','runner-owner-inputs'): continue
        if artifact.suffix in ('.su','.s') or '.ltrans' in name or '.wpa' in name or '.lto' in name or name.endswith(('.cgraph','.inline')):
            expected_artifacts.add(str(relative))
            if artifact.suffix == '.su' and str(relative) not in pre_su: backend.append(str(relative))
    assert seen == expected_artifacts and inventory['possible_backend_stack_files'] == backend
    stack_path = folder/'pre-lto-stack-records.json'
    if stack_path.exists():
        stack = read(stack_path)
        assert stack['scope'] == 'Conventional fat-object frames; not final LTO stack evidence'
        expected = []
        for unit in AVR_UNITS:
            for line in (folder/(unit+'.su')).read_text().splitlines():
                location,count,qualification = line.split('\t')
                assert qualification in ('static','dynamic,bounded')
                expected.append(dict(phase='pre-LTO fat-object compilation',unit=unit,location=location,
                    function=location.split(':',3)[3],bytes=int(count),qualification=qualification))
        assert stack['records'] == expected
    link = [row for row in report['commands'] if row['name'] == 'avr-link']
    observed = dict(linkInvoked=bool(link),linkCommandPassed=bool(link and link[0]['passed']),
        linkedElfPresent=(folder/'runtime.elf').exists(),artifactFiles=len(seen),
        possibleBackendStackFiles=backend,resourceArithmeticAudited=False,combinedStackProof=False,
        targetRuntimeFitDemonstrated=False)
    if link:
        errors = (folder/'avr-link.stderr').read_text()
        overflow = re.findall(r'overflowed by ([0-9]+) bytes',errors)
        observed['reportedRegionOverflowBytes'] = [int(value) for value in overflow]
    if not report['requested_checks_completed']:
        return observed
    avr = report['avr']; assert link and link[0]['passed'] and observed['linkedElfPresent']
    assert avr['mcu'] == 'atmega328p' and avr['declared_f_cpu_hz'] == 16000000
    assert avr['limits'] == dict(physical_flash=32768,uno_application_flash=32256,sram=2048,eeprom=1024)
    assert avr['target_executed'] is False and avr['target_runtime_fit_demonstrated'] is False
    assert avr['retention_policy_changed_from_parent'] is False and not avr['previously_unlinked_roots_added']
    sections = {}
    for line in (folder/'avr-sections.stdout').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].startswith('.'): sections[fields[0]] = int(fields[1])
    assert sections == avr['sections']
    symbols = []
    for line in (folder/'avr-symbols.stdout').read_text().splitlines():
        fields = line.split()
        if len(fields) == 4:
            address,size,kind,name = fields
            symbols.append(dict(address=int(address,16),bytes=int(size,16),type=kind,name=name))
    assert symbols == read(folder/'symbols.json')
    allocations = {row['name']:row['bytes'] for row in symbols if row['type'] in 'BbDd'}
    assert allocations == avr['allocations']
    retention = read(folder/'retention.json')
    functions = [row['name'] for row in retention['function_roots']]
    storage = {row['name']:row['bytes'] for row in retention['storage_roots']}
    assert len(functions) == 29 and len(storage) == 9
    assert avr['retained_function_roots'] == functions and avr['retained_storage_roots'] == storage
    executable = {row['name'] for row in symbols if row['type'] in 'Tt'}
    assert set(functions+retention['other_required_symbols']) <= executable
    assert {'main','__vector_13','__vector_18'} <= executable
    assert not {row['name'] for row in symbols} & {'malloc','calloc','realloc','free','alloca'}
    assert all(allocations.get(name) == count for name,count in storage.items())
    charged = sorted((row for row in symbols if row['name'] in storage),key=lambda row:row['address'])
    assert charged == avr['charged_storage_ranges'] and len(charged) == 9
    assert all(row['type'] in 'BbDd' and 0x800100 <= row['address'] and
               row['address']+row['bytes'] <= 0x800900 for row in charged)
    assert all(a['address']+a['bytes'] <= b['address'] for a,b in zip(charged,charged[1:]))
    assert allocations['hms_target_arena'] == 256 and allocations['hms_target_protection_reserve'] == 64
    assert sum(allocations[name] for name in ('hms_target_standing','hms_target_controller','hms_target_glue_reserve'))+2 == 160
    flash = sections.get('.text',0)+sections.get('.data',0)
    static = sum(sections.get(name,0) for name in ('.data','.bss','.noinit'))
    assert avr['flash_bytes'] == flash and avr['static_sram_bytes'] == static
    assert avr['static_plus_512_stack_bytes'] == static+512
    assert avr['new_static_delta_from_sealed_baseline'] == static-1343
    assert avr['standing_static_delta_ceiling_fits'] == (static-1343 <= 160)
    arithmetic = flash <= 32256 and static+512 <= 2048 and static-1343 <= 160
    assert avr['static_reservation_arithmetic_fits'] == arithmetic
    observed.update(resourceArithmeticAudited=True,flashBytes=flash,staticBytes=static,
        staticPlus512Bytes=static+512,staticDeltaBytes=static-1343,physicalFlashWithinLimit=flash<=32768,
        applicationFlashWithinLimit=flash<=32256,staticReservationArithmeticFits=arithmetic)
    return observed


def main(expected_native, expected_avr):
    assert (expected_native,expected_avr) == (NATIVE_RECEIPT_SHA256,AVR_RECEIPT_SHA256)
    before = snapshot(); attempts = []; identities = set(); total_commands = 0; reports = []
    expected_sources = fixed_sources(); assert len(expected_sources) == 139
    receipts = sorted(HERE.glob('checks-*.json'))
    assert [path.name for path in receipts] == ['checks-avr.json','checks-native.json']
    assert digest(HERE/'checks-native.json') == expected_native
    assert digest(HERE/'checks-avr.json') == expected_avr
    for path in receipts:
        report = read(path); folder = HERE/report['frozen_source_copy_root']
        assert report['attempt'] == 1 and report['stage'] in ('native','avr')
        assert folder == HERE/'build'/report['stage']
        sources = report['sources']
        assert sources == expected_sources
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
        plan = native_plan() if report['stage'] == 'native' else AVR_PLAN
        assert [command['name'] for command in commands] == plan[:len(commands)]
        assert len(commands) <= len(plan)
        if report['requested_checks_completed']: assert len(commands) == len(plan)
        else: assert report.get('error')
        failures = []
        for command in commands:
            name = command['name']; result = read(folder/(name+'.result.json'))
            check_compile_selection(command,folder)
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
        observed = check_avr(report,folder) if report['stage'] == 'avr' else (
            check_native(report,folder) if report['requested_checks_completed'] else {'nativeCompleted':False})
        if failures:
            assert len(failures) == 1 and failures[0]['command'] == commands[-1]['name']
        attempts.append(dict(receipt=path.name,sha256=digest(path),stage=report['stage'],attempt=report['attempt'],
                             completed=report['requested_checks_completed'],commands=len(commands),reaps=len(reaped),
                             failures=failures,observed=observed))
        reports.append(report)
    total_reaps = sum(len(report['owned_children_reaped']) for report in reports)
    assert total_commands == total_reaps == len(identities) == 58
    current = read(HERE/'project-source-review.json')
    assert digest(HERE/'project-source-review.json') == CURRENT_REVIEW_SHA256
    assert len(current['project_sha256']) == 41 and len(current['original_project_sha256']) == 40
    assert all(digest(HERE/'project'/name) == pin for name,pin in current['project_sha256'].items())
    assert digest(HERE/'project.diff') == current['project_delta_sha256']
    assert digest(HERE/'run_checks.py') == current['runner_sha256']
    assert digest(HERE/'runner-diff.patch') == current['runner_delta_sha256']
    prepared=current['all_other_prepared_files_sha256']
    assert len(prepared) == 138 and all(digest(contained(HERE,name)) == value for name,value in prepared.items())
    assert expected_sources == dict(prepared,**{'project-source-review.json':CURRENT_REVIEW_SHA256})
    for report in reports:
        assert {name.removeprefix('project/'):pin for name,pin in report['sources'].items()
                if name.startswith('project/')} == current['project_sha256']
    by_stage = {report['stage']:report for report in reports}; assert len(by_stage) == 2
    assert by_stage['native']['requested_checks_completed'] and len(by_stage['native']['commands']) == 34
    assert not by_stage['avr']['requested_checks_completed'] and len(by_stage['avr']['commands']) == 24
    assert by_stage['avr']['commands'][-1]['name'] == 'avr-link'
    avr_observed=next(attempt['observed'] for attempt in attempts if attempt['stage']=='avr')
    assert avr_observed['reportedRegionOverflowBytes'] == [6418]
    assert not avr_observed['linkedElfPresent'] and not avr_observed['linkCommandPassed']
    assert not avr_observed['resourceArithmeticAudited']
    parents = [
        ('artifacts/implementation/standing-endpoint-shared-kernel','0a4a518555e08415a9d893bba106616323a3f1a237b61bf0bc171ee8f2979909'),
        ('artifacts/design/standing-endpoint-phase-size','358207f52b904bcb6bb717e83b06846904ac56b9d4b295b85a68cd8f03559a27')]
    parent_counts = {name:verify_index(ROOT/name,pin) for name,pin in parents}
    assert digest(ROOT/parents[0][0]/'audit_retained.py') == PARENT_AUDIT_SHA256
    assert digest(HERE/'audit-parent.py') == PARENT_AUDIT_SHA256
    source_pins=read(HERE/'source-pins.json');originals=source_pins['originals'];assert len(originals) == 40
    assert originals == current['original_project_sha256'] and source_pins['project'] == current['project_sha256']
    for name,pin in originals.items():
        assert digest(contained(HERE/'originals/project',name)) == digest(contained(ROOT/parents[0][0]/'project',name)) == pin
    baseline=read(HERE/'baseline-pins.json')
    assert baseline['parentIndexSha256'] == parents[0][1] and len(baseline['projectFiles']) == 40
    for row in baseline['projectFiles']:
        source=contained(ROOT,row['source']);target=contained(HERE,row['copy'])
        assert digest(source) == digest(target) == row['sha256'] and target.stat().st_size == row['bytes']
    runner_pins=read(HERE/'runner-input-pins.json')
    for key in ('runner','baseline','delta'):
        row=runner_pins[key];assert digest(contained(HERE,row['path'])) == row['sha256']
    assert digest(HERE/'runner-baseline.py') == digest(HERE/'originals/run_checks.py') == digest(ROOT/parents[0][0]/'run_checks.py')
    for row in read(HERE/'runner-owner-pins.json')['files']:
        assert digest(contained(HERE,row['target'])) == digest(contained(ROOT,row['source'])) == row['sha256']
        assert (HERE/row['target']).stat().st_size == row['bytes']
    history_counts = {}
    for name in ('core-draft01','controls-draft01','controls-draft02','controls-draft03'):
        history_counts[name] = verify_index(HERE/'history'/name,prepared['history/'+name+'/index.json'])
    coverage = read(HERE/'native-coverage.json')
    baseline = (HERE/coverage['baseline_source']).read_bytes()
    active = (HERE/coverage['current_source']).read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == coverage['baseline_sha256']
    assert hashlib.sha256(active).hexdigest() == coverage['current_sha256']
    assert coverage['schema'] == 'hms-phase-kernel-native-coverage/1'
    assert len(coverage['unchanged_case_bodies']) == 14 and baseline == active
    assert coverage['baseline_case_order'] == coverage['current_case_order']
    assert [row['name'] for row in coverage['unchanged_case_bodies']] == coverage['baseline_case_order']
    for row in coverage['unchanged_case_bodies']:
        a,b = row['baseline_span']; c,d = row['current_span']
        assert baseline[a:b] == active[c:d]
        assert hashlib.sha256(baseline[a:b]).hexdigest() == row['sha256']
    assert len(coverage['other_unchanged_functions']) == 5
    for row in coverage['other_unchanged_functions']:
        old=contained(HERE,row['baseline_source']).read_bytes();new=contained(HERE,row['current_source']).read_bytes()
        a,b=row['baseline_span'];c,d=row['current_span']
        assert 0<=a<b<=len(old) and 0<=c<d<=len(new)
        assert old[a:b] == new[c:d] and hashlib.sha256(old[a:b]).hexdigest() == row['sha256']
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
    assert fixed_sources() == expected_sources
    result = dict(passed=True,auditSourceSha256=digest(Path(__file__)),parentAuditSha256=PARENT_AUDIT_SHA256,
                  attempts=attempts,totalCommands=total_commands,totalReaps=total_reaps,
                  observedOwnedIdentitiesAbsent=len(identities),currentProjectFiles=41,originalCopies=40,
                  frozenInputsExact=len(expected_sources),publicInputsExact=244,parentFilesExact=parent_counts,
                  oldStandingCaseBodiesExact=14,otherOldControlBodiesExact=5,historyFilesExact=history_counts,
                  currentSourcesNativeCompleted=by_stage['native']['requested_checks_completed'],
                  currentSourcesAvrCompleted=by_stage['avr']['requested_checks_completed'],
                  targetFitEstablished=False,combinedStackProof=False,
                  candidateCodeImported=False,checksRerun=False,targetExecuted=False,physicalIOQualified=False,
                  scope='Retained byte/receipt joins and observed process-identity absence. Native fixed-corpus equivalence and linked section arithmetic, if available, are explicit observations; audit pass never establishes final stack, timing, runtime fit or physical qualification.',
                  retainedFiles=before)
    with (HERE/'AUDIT.json').open('x') as target:
        json.dump(result,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({key:value for key,value in result.items() if key!='retainedFiles'},sort_keys=True))


if __name__ == '__main__':
    assert len(sys.argv) == 3 and all(re.fullmatch(r'[0-9a-f]{64}',value) for value in sys.argv[1:])
    main(sys.argv[1],sys.argv[2])
