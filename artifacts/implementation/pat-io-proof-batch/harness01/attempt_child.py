"""IoRuns15 child: isolated startup, exact selected tests and scoped origin evidence."""
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import sysconfig
import traceback

MAX_JSON = 4 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_ORIGINS = 8192
configuration = Path(sys.argv[1])
if configuration.stat().st_size > MAX_JSON:
    raise RuntimeError('Oversized child configuration')
config = json.loads(configuration.read_text())
root = Path(config['project']).resolve()
out = Path(config['attempt']).resolve()
sys.path[:0] = [str(root), str(root / 'tests')] + config['externalRoots']
sys.dont_write_bytecode = True
acquired = {str((root / value['path']).resolve()): value['sha256'] for value in config['expectedInputs']}
external = {value['resolvedPath']: value['sha256'] for value in config['expectedExternalInputs']}
stdlib = Path(sysconfig.get_path('stdlib')).resolve()
executed, resource_reads, denied_bytecode = set(), set(), set()
prohibited = []
current_test = None
sqlite_connections = []
scratch = Path(config['scratch']).resolve()
errors = []
counts = origins = None
loaded_ids, executed_ids = [], []
own_path = Path(__file__).resolve()


def sha(path):
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise RuntimeError('Origin file missing or exceeds acquisition bound')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


if sha(own_path) != config['childSha256']:
    raise RuntimeError('Retained child bytes differ from launcher pin')


def remember(collection, value):
    collection.add(value)
    if len(collection) > MAX_ORIGINS:
        raise RuntimeError('Actual-origin inventory exceeds fixed bound')


def is_stdlib(path):
    return path.is_relative_to(stdlib) and not {'site-packages', 'dist-packages'}.intersection(path.parts)


CONTROL_TARGETS = ['test_pat_io_definition_build.DefinitionBuildTests.test_build_is_pure_and_does_not_read_authority_or_current_sources', 'test_pat_io_definition_build.DefinitionBuildTests.test_changed_generations_are_rederived_on_each_build', 'test_pat_io_definition_build.DefinitionBuildTests.test_invalid_proof_inputs_keep_original_refusal_type_and_code', 'test_pat_io_definition_build.DefinitionBuildTests.test_multiple_actions_share_only_their_own_instance_proof', 'test_pat_io_definition_build.DefinitionBuildTests.test_original_bundles_bindings_and_proofs_match_with_half_the_derivations', 'test_pat_io_definition_build.DefinitionBuildTests.test_public_handler_details_still_derives_a_fresh_proof_per_call', 'test_pat_io_definition_build.DefinitionBuildTests.test_returned_mutation_changes_neither_input_nor_later_builds', 'test_pat_io_installation_reuse.InstallationReuseTests.test_changed_current_source_refuses_even_with_warm_exact_input', 'test_pat_io_installation_reuse.InstallationReuseTests.test_changed_helper_bypasses_warm_result_and_runs_original_validation', 'test_pat_io_installation_reuse.InstallationReuseTests.test_concurrent_calls_keep_one_entry_and_detached_results', 'test_pat_io_installation_reuse.InstallationReuseTests.test_custom_values_and_keys_refuse_without_callbacks_or_lookup', 'test_pat_io_installation_reuse.InstallationReuseTests.test_dependency_changed_during_validation_prevents_publication', 'test_pat_io_installation_reuse.InstallationReuseTests.test_identical_object_and_bytes_reuse_semantics_but_check_source_each_time', 'test_pat_io_installation_reuse.InstallationReuseTests.test_in_place_primitive_configuration_change_uses_current_validation', 'test_pat_io_installation_reuse.InstallationReuseTests.test_integral_float_in_object_or_json_refuses_before_lookup', 'test_pat_io_installation_reuse.InstallationReuseTests.test_ninth_valid_input_evicts_oldest_with_fixed_key_and_entry_bounds', 'test_pat_io_installation_reuse.InstallationReuseTests.test_noncanonical_bytes_share_key_but_duplicate_or_oversized_json_refuses', 'test_pat_io_installation_reuse.InstallationReuseTests.test_private_schema_and_keyword_changes_disable_reuse', 'test_pat_io_installation_reuse.InstallationReuseTests.test_replaced_topology_or_generation_validator_refuses_warm_input', 'test_pat_io_installation_reuse.InstallationReuseTests.test_returned_nested_mutation_never_changes_caller_or_later_results', 'test_pat_io_installation_reuse.InstallationReuseTests.test_reuse_never_opens_authority_launches_provider_or_reads_clock', 'test_resource_topology.ResourceTopologyTests.test_alias_depth_and_node_count_limits_refuse_without_truncation', 'test_resource_topology.ResourceTopologyTests.test_all_graph_cycle_classes_and_multiple_parent_refuse', 'test_resource_topology.ResourceTopologyTests.test_bus_address_bounds_duplicate_and_cross_bus_refuse', 'test_resource_topology.ResourceTopologyTests.test_bus_raw_and_addressed_share_controller_and_pins', 'test_resource_topology.ResourceTopologyTests.test_closed_shape_duplicate_consumer_and_carrier_refusals', 'test_resource_topology.ResourceTopologyTests.test_consumer_and_lifecycle_claim_bounds_are_separate', 'test_resource_topology.ResourceTopologyTests.test_electrical_range_mode_and_exact_integer_refusals', 'test_resource_topology.ResourceTopologyTests.test_exact_atom_coverage_duplicate_purpose_and_namespace_refuse', 'test_resource_topology.ResourceTopologyTests.test_generations_close_exactly_and_do_not_claim_historical_nonreuse', 'test_resource_topology.ResourceTopologyTests.test_gpio_pwm_overlap_and_independent_pad_have_exact_atoms', 'test_resource_topology.ResourceTopologyTests.test_lifecycle_covers_sibling_action_of_rebound_instance_without_locking_unrelated_instance', 'test_resource_topology.ResourceTopologyTests.test_lifecycle_scope_is_reverse_dependencies_not_whole_hub', 'test_resource_topology.ResourceTopologyTests.test_missing_and_wrong_kind_references_including_unused_access_refuse', 'test_resource_topology.ResourceTopologyTests.test_missing_or_shrunken_pwm_alias_refuses', 'test_resource_topology.ResourceTopologyTests.test_order_normalization_and_detachment', 'test_resource_topology.ResourceTopologyTests.test_relevant_electrical_and_driver_implementation_changes_visible', 'test_resource_topology.ResourceTopologyTests.test_schema_outputs_and_pure_calls_do_not_open_authority', 'test_resource_topology.ResourceTopologyTests.test_scoped_identity_excludes_unrelated_properties_and_structural_containment', 'test_resource_topology.ResourceTopologyTests.test_sibling_expansion_overflow_refuses_even_when_direct_dependents_fit', 'test_resource_topology.ResourceTopologyTests.test_unrelated_generation_is_ignored_relevant_generation_changes_binding', 'test_resource_topology.ResourceTopologyTests.test_unsupported_and_oversized_objects_refuse_before_copy_or_recursive_walk', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_binding_identity_tracks_changed_electrical_inputs_after_warmup', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_exact_bytes_and_reordered_object_keys_reuse_only_schema_success', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_exact_changed_footprint_is_revalidated_and_rejected', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_generations_still_require_exact_current_topology_and_node_closure', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_lru_capacity_and_eviction_are_bounded_without_truncating_input', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_returned_nested_data_cannot_mutate_cache_or_other_results', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_invalid_documents_are_never_cached', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_replacement_cannot_inherit_cached_success', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_success_does_not_suppress_repeated_graph_failure', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_warm_entry_does_not_accept_integral_float_bool_or_duplicate_json_keys', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_warm_snapshot_remains_pure_and_does_not_consult_caller_copy_hooks', 'test_pat_io_proof_batch.ProofBatchTests.test_concurrent_builds_keep_distinct_static_inputs', 'test_pat_io_proof_batch.ProofBatchTests.test_each_call_observes_changed_generation_and_topology', 'test_pat_io_proof_batch.ProofBatchTests.test_exact_build_with_one_validation_and_four_separate_proofs', 'test_pat_io_proof_batch.ProofBatchTests.test_fixed_interleaved_build_measurements', 'test_pat_io_proof_batch.ProofBatchTests.test_invalid_inputs_preserve_original_first_refusal', 'test_pat_io_proof_batch.ProofBatchTests.test_public_handler_calls_never_use_private_build_snapshot', 'test_pat_io_proof_batch.ProofBatchTests.test_public_proof_matches_original_body_for_gpio_pwm_bus_and_generations', 'test_pat_io_proof_batch.ProofBatchTests.test_replaced_public_proof_helper_keeps_original_call_path', 'test_pat_io_proof_batch.ProofBatchTests.test_returned_mutations_do_not_alias_other_instances_or_future_calls', 'test_pat_io_proof_batch.ProofBatchTests.test_untrusted_topology_value_refuses_without_copy_hook']

def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Control selection forbids network and subprocesses')
    if event == 'sqlite3.connect':
        prohibited.append(event); raise RuntimeError('Pure definition/normalization tests forbid all SQLite opens')
    if event == 'exec':
        origin = args[0].co_filename
        remember(executed, origin)
        if isinstance(origin, str) and not origin.startswith('<'):
            path = Path(origin).resolve()
            expected = acquired.get(str(path), external.get(str(path)))
            if expected is not None:
                if sha(path) != expected:
                    raise RuntimeError('Executable source changed after acquisition')
            elif path != own_path and not is_stdlib(path):
                raise RuntimeError('Executable origin outside acquired source/selected dependencies')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        if path.suffix == '.pyc':
            remember(denied_bytecode, str(path))
            raise FileNotFoundError(2, 'Use exact retained source, not cached bytecode', str(path))
        if path.is_absolute() and any(path.is_relative_to(Path(base)) for base in config['externalRoots']):
            remember(resource_reads, str(path))


sys.addaudithook(audit)


def write(name, value):
    encoded = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_JSON:
        raise RuntimeError('Child JSON receipt exceeds fixed emission bound')
    (out / name).write_bytes(encoded)


def actual_origins():
    rows, violations, seen = [], [], set()
    def add(label, origin):
        if not isinstance(origin, str) or origin.startswith('<') or origin in {'built-in', 'frozen'}:
            rows.append({'source': label, 'origin': str(origin), 'kind': 'interpreter_or_synthetic'})
            return
        path = Path(origin).resolve()
        key = (label, str(path))
        if key in seen:
            return
        if len(rows) >= MAX_ORIGINS:
            raise RuntimeError('Actual-origin report exceeds fixed record bound')
        seen.add(key)
        value = {'source': label, 'origin': str(path)}
        if not path.is_file():
            value['kind'] = 'missing'
            violations.append(value.copy())
            rows.append(value)
            return
        value['sha256'] = sha(path)
        if path.is_relative_to(root):
            value['kind'] = 'project'
            value['matchesBefore'] = acquired.get(str(path)) == value['sha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif str(path) in external:
            value['kind'] = 'selected_external'
            value['matchesBefore'] = external[str(path)] == value['sha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif path == own_path:
            value['kind'] = 'retained_child_harness'
            value['matchesBefore'] = value['sha256'] == config['childSha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif is_stdlib(path):
            value['kind'] = 'stdlib_actual_file'
            value['preExecutionPin'] = False
        else:
            value['kind'] = 'unexpected_origin'
            violations.append(value.copy())
        rows.append(value)
    for name, module in sorted(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if origin is None:
            origin = getattr(getattr(module, '__spec__', None), 'origin', None)
        if origin is not None:
            add('module:' + name, origin)
        if (name == 'hms' or name.startswith('hms.') or name.startswith('test_') or name == 'evidence' or name.startswith('evidence.') or name == 'evidence_compact' or name.startswith('evidence_compact.') or name == 'recorded_io' or name.startswith('recorded_io.')) and origin:
            if not Path(origin).resolve().is_relative_to(root):
                violations.append({'module': name, 'origin': str(origin), 'reason': 'project_name_outside_copy'})
    for origin in sorted(executed):
        add('executed_code', origin)
    # Snapshot before hash reads themselves emit further harmless open events.
    for origin in sorted(resource_reads):
        add('selected_external_read', origin)
    return {'profile': 'hms.io-correspondence-actual-origins/1',
            'summary': {'complete': True, 'allOriginsMatched': not violations and not prohibited,
                        'recordCount': len(rows), 'violationCount': len(violations),
                        'prohibitedAttemptCount': len(prohibited)},
            'records': rows, 'violations': violations, 'prohibitedAttempts': prohibited,
            'deniedBytecodeReads': sorted(denied_bytecode),
            'limits': 'Selected source/package origins are checked; startup stdlib and dynamically linked system libraries are not a full pre-execution closure. Frozen/synthetic code is distinct. Temporary identity-fixture resources are generated data, not imported code. Audit hooks are cooperative guardrails, not an OS sandbox.'}


def flatten(suite):
    import unittest
    result = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.extend(flatten(test))
        else:
            result.append(test.id())
    return result


try:
    if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode or
            len(config['targets']) != 63 or len(set(config['targets'])) != 63):
        raise RuntimeError('Required child isolation flags or exact target count missing')
    write('child-runtime.json', {'executable': sys.executable, 'version': sys.version,
        'flags': repr(sys.flags), 'path': sys.path, 'cwd': str(Path.cwd()),
        'environment': dict(os.environ), 'stdlib': str(stdlib)})
    import unittest
    from hms.pat_compiler import compiler_digest, compiler_manifest
    write('compiler-before.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    from hms.synthetic_io_installation import implementation_digest
    write('driver-before.json', {'digest': implementation_digest()})
    tests = unittest.defaultTestLoader.loadTestsFromNames(config['targets'])
    loaded_ids = flatten(tests)
    write('loader-errors.json', list(unittest.defaultTestLoader.errors))
    for detail in unittest.defaultTestLoader.errors: print(detail, file=sys.stderr, flush=True)
    if loaded_ids != config['targets']:
        raise RuntimeError('Loaded methods do not exactly match the reviewed runs15 selection')
    class RecordingResult(unittest.TextTestResult):
        def startTest(self, test):
            global current_test
            current_test = test.id()
            executed_ids.append(test.id())
            super().startTest(test)
        def stopTest(self, test):
            global current_test
            super().stopTest(test)
            current_test = None
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)
    counts = {'testsRun': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skips': len(result.skipped), 'expectedFailures': len(result.expectedFailures),
        'unexpectedSuccesses': len(result.unexpectedSuccesses)}
    write('compiler-after.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    write('driver-after.json', {'digest': implementation_digest()})
except BaseException as exc:
    errors.append({'type': type(exc).__name__, 'message': str(exc)[:4096]})
    traceback.print_exc()
finally:
    def finalize(label, callback):
        try:
            callback()
        except BaseException as exc:
            errors.append({'phase': label, 'type': type(exc).__name__, 'message': str(exc)[:4096]})
    def origins_receipt():
        global origins
        origins = actual_origins()
        write('imports.json', origins)
    finalize('actual-origins', origins_receipt)
    finalize('sqlite-connections', lambda: write('sqlite-connections.json', sqlite_connections))
    finalize('exact-methods', lambda: write('actual-tests.json', {'loaded': loaded_ids, 'executed': executed_ids,
        'exactSelection': loaded_ids == config['targets'] == executed_ids}))
    if counts is not None:
        finalize('test-return', lambda: write('test-return.json', counts))
    try:
        write('child-errors.json', errors)
    except BaseException:
        errors.append({'phase': 'child-errors', 'type': 'ReceiptWriteFailure'})
passed = (not errors and counts is not None and counts['testsRun'] == 63 and
    all(counts[key] == 0 for key in counts if key != 'testsRun') and
    loaded_ids == config['targets'] == executed_ids and origins is not None and
    origins['summary']['allOriginsMatched'])
raise SystemExit(0 if passed else 1)
