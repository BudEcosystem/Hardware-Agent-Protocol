"""Original isolated history107 runner. Execute only after parent review/release.

No project imports occur in this launcher. Seven selected distribution closures
are acquired independently of the compiler's seven-package identity.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import _sqlite3

PACKAGES = ('jsonschema', 'referencing', 'jsonschema-specifications', 'attrs',
            'rpds-py', 'typing_extensions', 'idna')
FROZEN_INDEX = 'ad22248967c7a163ccd108d13210331399e15ffb9e166541a80694dce649547c'
PREFIX = 'artifacts/implementation/pat-io-group-history/implementation04/'
MAX_FILE = 16 * 1024 * 1024
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_FILES = 8192
MAX_JSON = 4 * 1024 * 1024
MAX_LOG = 8 * 1024 * 1024
MAX_SCRATCH_BYTES = 16 * 1024 * 1024
OWN_FILES = ('run_attempt.py', 'attempt_child.py', 'targets.json', 'SCOPE.md',
             'references/approved-external-roots.json', 'borrowed-inputs.json')


def digest(path):
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('File is missing or exceeds acquisition bound: ' + str(path))
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def row(path, relative):
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Only regular non-symlink input files are supported: ' + str(path))
    return {'path': relative, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError('JSON receipt is missing, linked or oversized: ' + str(path))
    return json.loads(path.read_text())


def write_json(path, value):
    encoded = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_JSON:
        raise ValueError('JSON receipt exceeds emission bound: ' + str(path))
    path.write_bytes(encoded)


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {'..', '.'} for part in path.parts):
        raise ValueError('Unsafe retained relative path')
    return path


def inventory(directory, *, max_bytes=MAX_INPUT_BYTES):
    rows, total = [], 0
    for base, directories, filenames in os.walk(directory, followlinks=False):
        for name in directories:
            if (Path(base) / name).is_symlink():
                raise ValueError('Linked directory in retained tree')
        for name in filenames:
            path = Path(base) / name
            record = row(path, str(path.relative_to(directory)))
            rows.append(record)
            total += record['bytes']
            if len(rows) > MAX_FILES or total > max_bytes:
                raise ValueError('Retained tree exceeds collection bound')
    return sorted(rows, key=lambda value: value['path'])


def frozen_inputs(stage):
    index = stage / 'index.json'
    if digest(index) != FROZEN_INDEX:
        raise ValueError('Frozen source-preparation index changed')
    value = read_json(index)
    expected = value['files']
    if len(expected) != 4201:
        raise ValueError('Frozen inventory count changed')
    actual = []
    for expected_row in expected:
        name = expected_row['path']
        if not name.startswith(PREFIX):
            raise ValueError('Input escaped frozen stage prefix')
        relative = safe_relative(name[len(PREFIX):])
        acquired = row(stage / relative, name)
        if acquired != expected_row:
            raise ValueError('Frozen input changed: ' + name)
        actual.append(acquired)
    return actual


def selected_external(approved):
    metadata = {value['package']: value for value in approved['selectedMetadata']}
    if set(metadata) != set(PACKAGES):
        raise ValueError('Selected distribution set is not the closed seven-package set')
    approved_roots = {str(Path(value).resolve()) for value in approved['roots']}
    rows, exclusions, roots, total = [], [], set(), 0
    for package in PACKAGES:
        distribution = importlib.metadata.distribution(package)
        root = Path(distribution.locate_file('')).resolve()
        pin = metadata[package]
        if str(root) not in approved_roots or distribution.version != pin['version']:
            raise ValueError('Selected distribution root/version differs from reviewed pin')
        metadata_path = Path(pin['metadataPath'])
        if row(metadata_path, str(metadata_path)) != {
                'path': str(metadata_path), 'bytes': pin['bytes'], 'sha256': pin['sha256']}:
            raise ValueError('Selected metadata differs from reviewed pin')
        roots.add(str(root))
        if not distribution.files:
            raise ValueError('Selected distribution has no inventoried files')
        for item in sorted(distribution.files, key=str):
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts or item.suffix == '.pyc':
                exclusions.append({'package': package, 'path': str(item),
                                   'reason': 'non-package-path-or-bytecode-cache'})
                continue
            path = Path(distribution.locate_file(item))
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError('Selected file resolves outside reviewed package root')
            acquired = row(path, str(item))
            acquired.update(package=package, version=distribution.version, resolvedPath=str(resolved))
            rows.append(acquired)
            total += acquired['bytes']
            if len(rows) > MAX_FILES or total > MAX_INPUT_BYTES:
                raise ValueError('Selected dependencies exceed acquisition bound')
    for label, path in [('python', Path(sys.executable).resolve()),
                        ('sqlite-extension', Path(_sqlite3.__file__).resolve())]:
        acquired = row(path, str(path))
        acquired.update(runtime=label, resolvedPath=str(path))
        rows.append(acquired)
    return {'files': rows, 'roots': sorted(roots), 'excludedRecords': exclusions,
            'pythonVersion': sys.version, 'sqliteVersion': _sqlite3.sqlite_version}


def stop_owned(process, record):
    if process is None:
        record['childState'] = 'not_started'
        return
    for action in ('terminate', 'kill'):
        if process.poll() is not None:
            break
        try:
            getattr(process, action)()
            record.setdefault('signalsAttempted', []).append(action)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            break
    record['exitCode'] = process.poll()
    record['childState'] = 'exited' if process.returncode is not None else 'termination_unconfirmed'


def collect(process, log, deadline):
    """Bound retained pipe bytes and wall wait; only this owned child is stopped."""
    count = 0
    with selectors.DefaultSelector() as selector:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('IoGroupHistory107 child exceeded original harness deadline')
            for key, _ in selector.select(min(remaining, 0.1)):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                if count + len(block) > MAX_LOG:
                    log.write(block[:MAX_LOG - count])
                    log.flush()
                    raise ValueError('Child output exceeded fixed retained log bound')
                log.write(block)
                count += len(block)
            if time.monotonic() >= deadline:
                raise TimeoutError('IoGroupHistory107 child crossed harness deadline during pipe collection')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('IoGroupHistory107 child crossed harness deadline at EOF')
    process.wait(timeout=remaining)
    if time.monotonic() >= deadline:
        raise TimeoutError('IoGroupHistory107 child crossed harness deadline at process exit')
    return count


def counts_pass(value):
    names = {'testsRun', 'failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'}
    return (type(value) is dict and set(value) == names and
            all(type(value[key]) is int and value[key] >= 0 for key in names) and
            value['testsRun'] == 107 and all(value[key] == 0 for key in names - {'testsRun'}))


def scratch_identity(path):
    """Identify the original private directory without following a root symlink."""
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError('Raw scratch must be an actual directory')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt')
    parser.add_argument('--parent-released', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    if not args.parent_released:
        raise SystemExit('Execution remains held: explicit parent source-review release is required.')
    if (not args.attempt or len(args.attempt) > 64 or
            not args.attempt.replace('-', '').replace('_', '').isalnum() or
            not 1 <= args.timeout_seconds <= 180):
        raise SystemExit('Invalid attempt name or bounded timeout')
    here = Path(__file__).resolve().parent
    stage = here.parent / 'implementation04'
    attempt = here / 'attempts' / args.attempt
    attempt.mkdir(parents=True, mode=0o700, exist_ok=False)
    tree = attempt / 'project'
    process = None
    scratch = None
    scratch_before = scratch_parent_before = None
    before = external_before = frozen_before = own_before = None
    started = time.monotonic()
    record = {'profile': 'hms.io-group-worker-attempt/1', 'attempt': args.attempt,
              'status': 'preparing', 'currentPass': False, 'childState': 'not_started',
              'exitCode': None, 'counts': None, 'errors': [], 'expectedTests': 107,
              'projectInputCount': 4198, 'frozenPreparationInputCount': 4201,
              'timeoutSeconds': args.timeout_seconds, 'totalDiskQuotaEnforced': False,
              'limits': {'singleAcquiredFileBytes': MAX_FILE, 'inventoryFiles': MAX_FILES,
                         'inputInventoryBytes': MAX_INPUT_BYTES, 'jsonReceiptBytes': MAX_JSON,
                         'retainedLogBytes': MAX_LOG, 'scratchRetentionBytes': MAX_SCRATCH_BYTES},
              'scope': 'Exact current group/budget selection; no network, physical endpoint, MCU, inference or live service.'}
    write_json(attempt / 'started.json', record)
    try:
        own_before = [row(here / name, name) for name in OWN_FILES]
        write_json(attempt / 'harness-before.json', own_before)
        for name in OWN_FILES:
            target = attempt / 'harness' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(here / name, target)
        frozen_before = frozen_inputs(stage)
        write_json(attempt / 'frozen-before.json', frozen_before)
        selected = [value for value in frozen_before if value['path'].startswith(PREFIX + 'project/')]
        if len(selected) != 4198:
            raise ValueError('Candidate project closure must contain exactly 4198 files')
        for value in selected:
            relative = safe_relative(value['path'][len(PREFIX + 'project/'):])
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / 'project' / relative, target)
        before = inventory(tree)
        expected = [dict(value, path=value['path'][len(PREFIX + 'project/'):]) for value in selected]
        if before != sorted(expected, key=lambda value: value['path']):
            raise ValueError('Copied project differs from frozen candidate inputs')
        write_json(attempt / 'inputs-before.json', before)
        approved = read_json(attempt / 'harness/references/approved-external-roots.json')
        external_before = selected_external(approved)
        write_json(attempt / 'external-before.json', external_before)
        targets = read_json(attempt / 'harness/targets.json')
        if (targets['testCount'] != 107 or
                len(targets['targets']) != 107 or
                len(set(targets['targets'])) != 107 or
                targets['targets'] != ['test_resource_topology.ResourceTopologyTests.test_alias_depth_and_node_count_limits_refuse_without_truncation', 'test_resource_topology.ResourceTopologyTests.test_all_graph_cycle_classes_and_multiple_parent_refuse', 'test_resource_topology.ResourceTopologyTests.test_bus_address_bounds_duplicate_and_cross_bus_refuse', 'test_resource_topology.ResourceTopologyTests.test_bus_raw_and_addressed_share_controller_and_pins', 'test_resource_topology.ResourceTopologyTests.test_closed_shape_duplicate_consumer_and_carrier_refusals', 'test_resource_topology.ResourceTopologyTests.test_consumer_and_lifecycle_claim_bounds_are_separate', 'test_resource_topology.ResourceTopologyTests.test_electrical_range_mode_and_exact_integer_refusals', 'test_resource_topology.ResourceTopologyTests.test_exact_atom_coverage_duplicate_purpose_and_namespace_refuse', 'test_resource_topology.ResourceTopologyTests.test_generations_close_exactly_and_do_not_claim_historical_nonreuse', 'test_resource_topology.ResourceTopologyTests.test_gpio_pwm_overlap_and_independent_pad_have_exact_atoms', 'test_resource_topology.ResourceTopologyTests.test_lifecycle_covers_sibling_action_of_rebound_instance_without_locking_unrelated_instance', 'test_resource_topology.ResourceTopologyTests.test_lifecycle_scope_is_reverse_dependencies_not_whole_hub', 'test_resource_topology.ResourceTopologyTests.test_missing_and_wrong_kind_references_including_unused_access_refuse', 'test_resource_topology.ResourceTopologyTests.test_missing_or_shrunken_pwm_alias_refuses', 'test_resource_topology.ResourceTopologyTests.test_order_normalization_and_detachment', 'test_resource_topology.ResourceTopologyTests.test_relevant_electrical_and_driver_implementation_changes_visible', 'test_resource_topology.ResourceTopologyTests.test_schema_outputs_and_pure_calls_do_not_open_authority', 'test_resource_topology.ResourceTopologyTests.test_scoped_identity_excludes_unrelated_properties_and_structural_containment', 'test_resource_topology.ResourceTopologyTests.test_sibling_expansion_overflow_refuses_even_when_direct_dependents_fit', 'test_resource_topology.ResourceTopologyTests.test_unrelated_generation_is_ignored_relevant_generation_changes_binding', 'test_resource_topology.ResourceTopologyTests.test_unsupported_and_oversized_objects_refuse_before_copy_or_recursive_walk', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_binding_identity_tracks_changed_electrical_inputs_after_warmup', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_exact_bytes_and_reordered_object_keys_reuse_only_schema_success', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_exact_changed_footprint_is_revalidated_and_rejected', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_generations_still_require_exact_current_topology_and_node_closure', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_lru_capacity_and_eviction_are_bounded_without_truncating_input', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_returned_nested_data_cannot_mutate_cache_or_other_results', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_invalid_documents_are_never_cached', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_replacement_cannot_inherit_cached_success', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_schema_success_does_not_suppress_repeated_graph_failure', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_warm_entry_does_not_accept_integral_float_bool_or_duplicate_json_keys', 'test_resource_schema_memo.ResourceSchemaMemoTests.test_warm_snapshot_remains_pure_and_does_not_consult_caller_copy_hooks', 'test_pat_io_group_worker.IoGroupBudgetTests.test_negative_preflight_distinguishes_refused_and_not_applicable', 'test_pat_io_group_worker.IoGroupBudgetTests.test_case_tick_and_admission_limits_include_rejected_probe_reservations', 'test_pat_io_group_worker.IoGroupBudgetTests.test_closed_state_counts_toward_derived_closure_and_stops_on_overflow', 'test_pat_io_group_worker.IoGroupBudgetTests.test_combined_bytes_are_charged_before_any_writer', 'test_pat_io_group_worker.IoGroupBudgetTests.test_combined_records_include_reserved_terminal_and_span_cases', 'test_pat_io_group_worker.IoGroupBudgetTests.test_deadline_is_group_origin_and_regression_also_refuses', 'test_pat_io_group_worker.IoGroupBudgetTests.test_exact_case_order_cannot_skip_or_run_two_engines', 'test_pat_io_group_worker.IoGroupBudgetTests.test_incomplete_group_cannot_emit_success_or_reuse_terminal_reservation', 'test_pat_io_group_worker.IoGroupBudgetTests.test_mismatched_evidence_and_ticks_cannot_finish_a_ticket', 'test_pat_io_group_worker.IoGroupBudgetTests.test_program_mismatch_and_stale_ticket_refuse', 'test_pat_io_group_worker.IoGroupWorkerTests.test_changed_implementation_refuses_before_group_output', 'test_pat_io_group_worker.IoGroupWorkerTests.test_parameterized_matrix_refuses_before_runtime_or_output', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_all_cases_reference_complete_deduplicated_artifacts', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_auxiliary_actors_consume_the_global_operation_ceiling', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_changed_candidate_or_limits_invalidate_old_plan', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_clock_and_full_read_withdrawal_cases_require_worker_extensions', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_constant_gpio_and_pwm_include_all_required_cases_and_operations', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_different_endpoint_sessions_cannot_form_one_board_challenge', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_duplicate_actor_identity_refuses', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_exact_validation_is_stable_and_input_order_independent', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_explicit_cross_route_role_swap_is_supported', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_fault_success_requires_exact_effect_counts_and_zero_unresolved_work', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_fixed_timing_challenges_do_not_mutate_or_relabel_candidate', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_independent_pin_cannot_be_substituted_for_shared_alias', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_late_parent_preserves_completion_but_requires_nominal_timing_failure', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_limits_are_closed', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_limits_cannot_be_widened_or_use_numeric_aliases', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_lower_case_ceiling_refuses_without_dropping_challenges', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_omitted_or_extra_challenge_bindings_refuse', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_opaque_action_names_use_trusted_primitive_mapping', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_parameter_only_success_does_not_bypass_combined_case_limit', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_plan_integrity_rejects_rehashed_omissions_effects_and_success_flags', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_plan_is_bounded_json_and_never_claims_runtime_enforcement', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_planning_and_validation_are_pure_after_trusted_construction', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_resource_scenario_declares_both_primitives_cross_route_and_independent_progress', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_returned_plan_cannot_mutate_cached_topology_or_next_generation', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_same_route_alias_does_not_prove_cross_route_exclusion', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_serialized_plan_obeys_lower_document_and_derived_limits', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_sixteen_candidate_steps_and_all_challenges_share_one_operation_count', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_successful_candidate_cases_require_replay_and_conflict_without_extra_admission', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_target_must_be_the_explicitly_selected_challenge_binding', 'test_pat_io_combined_matrix.IoCombinedMatrixTests.test_tick_reservations_cover_all_trials', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_all_five_group_runner_families_reject_changed_inputs_before_runtime', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_all_five_input_documents_are_exactly_associated', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_all_five_standalone_runners_still_reconstruct_and_reject_a_changed_plan', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_budget_rejects_wrong_plan_type_or_mismatched_matrix', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_caller_mutation_and_returned_matrix_do_not_mutate_validated_bundle', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_constructor_preserves_full_preflight_and_original_limits', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_digest_and_matrix_match_independent_original_validation', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_equal_bytes_and_reordered_keys_preserve_detached_reuse', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_integral_float_and_bool_cannot_inherit_success_through_json_equivalence', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_oversized_or_unsupported_reuse_input_cannot_reach_comparison', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_repeated_exact_inputs_do_not_reconstruct_policy_or_consult_authority', 'test_pat_io_validated_matrix.ValidatedIoMatrixTests.test_ticket_requires_exact_plan_before_binding_and_cannot_reuse_stale_state', 'test_io_compact_storage.StorageProfileInputTests.test_unsupported_profiles_and_page_sizes_refuse_before_opening_state', 'test_pat_io_encoding.IoEncodingTests.test_base_exact_envelope_reuse_detachment_and_durability', 'test_pat_io_encoding.IoEncodingTests.test_base_expired_budget_precedes_encoding_and_file_creation', 'test_pat_io_encoding.IoEncodingTests.test_cached_record_still_checks_group_and_does_not_reserve_again', 'test_pat_io_encoding.IoEncodingTests.test_changed_value_and_nonreusable_write_preserve_original_sequence', 'test_pat_io_encoding.IoEncodingTests.test_combined_limits_keep_original_precedence_before_clock_check', 'test_pat_io_encoding.IoEncodingTests.test_configured_writer_encodes_once_and_keeps_both_streams_exact', 'test_pat_io_encoding.IoEncodingTests.test_exclusive_open_failure_preserves_existing_file_and_group_charge', 'test_pat_io_encoding.IoEncodingTests.test_fsync_failure_retains_bytes_without_publishing_reference_or_refund', 'test_pat_io_encoding.IoEncodingTests.test_topology_snapshot_encodes_once_for_objects_and_bytes_and_detaches', 'test_pat_io_group_history.IoGroupSetupTests.test_all_required_cases_have_individual_bounded_pre_run_setup', 'test_pat_io_group_history.IoGroupSetupTests.test_fault_and_permission_plans_are_selected_before_capture', 'test_pat_io_group_history.IoGroupSetupTests.test_reader_has_no_direct_producer_or_effect_imports', 'test_pat_io_group_history.IoGroupSetupTests.test_reader_refuses_incomplete_and_duplicate_expected_case_inventory', 'test_pat_io_group_history.IoGroupSetupTests.test_reader_rejects_archive_shapes_and_capacity_before_inspection', 'test_pat_io_group_history.IoGroupSetupTests.test_reader_rejects_scalar_coercion_and_noncanonical_result', 'test_pat_io_group_history.IoGroupSetupTests.test_setup_does_not_create_runtime_or_consult_authority_database', 'test_pat_io_group_history.IoGroupSetupTests.test_setup_requires_separate_exact_initial_authority', 'test_pat_io_group_history.IoGroupSetupTests.test_setup_snapshots_do_not_share_caller_or_case_mutations', 'test_pat_io_group_history.IoGroupSetupTests.test_absent_current_environment_requires_exact_authority_reopen_context', 'test_pat_io_group_history.IoGroupSetupTests.test_resource_environment_checks_all_four_original_and_current_actors']):
            raise ValueError('Closed history107 method selection changed')
        # Reuse the reviewed source08 ancestor/ownership checks; never chmod
        # a shared ancestor or delete the original raw scratch root.
        scratch_parent = Path('/tmp')
        scratch_parent_before = scratch_identity(scratch_parent)
        if (scratch_parent_before['uid'] not in {0, os.getuid()} or
                (scratch_parent_before['mode'] & 0o022 and
                 not scratch_parent_before['mode'] & stat.S_ISVTX)):
            raise ValueError('Trusted /tmp scratch ancestor is unavailable')
        scratch = Path(tempfile.mkdtemp(prefix='hms-io-group-history-history107-', dir=str(scratch_parent)))
        record['scratchPath'] = str(scratch)
        record['rawScratchPolicy'] = ('Never deleted by this runner; raw outputs must be '
                                      'explicitly acquired before operating-system /tmp cleanup.')
        scratch_before = scratch_identity(scratch)
        if (scratch_before['uid'] != os.getuid() or scratch_before['mode'] != 0o700 or
                scratch_identity(scratch_parent) != scratch_parent_before):
            raise ValueError('Original private scratch ownership or /tmp ancestor changed')
        write_json(attempt / 'raw-scratch-before.json', {
            'identity': scratch_before, 'parent': scratch_parent_before,
            'retentionPolicy': record['rawScratchPolicy']})
        environment = {'PATH': os.pathsep.join((str(Path(sys.executable).parent), '/usr/bin', '/bin')),
                       'TMPDIR': str(scratch), 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
        config = {'project': str(tree), 'attempt': str(attempt), 'targets': targets['targets'],
                  'scratch': str(scratch), 'externalRoots': external_before['roots'], 'expectedInputs': before,
                  'expectedExternalInputs': external_before['files'],
                  'childSha256': digest(attempt / 'harness/attempt_child.py')}
        write_json(attempt / 'child-config.json', config)
        command = [sys.executable, '-I', '-S', '-B', str(attempt / 'harness/attempt_child.py'),
                   str(attempt / 'child-config.json')]
        write_json(attempt / 'command.json', {'argv': command, 'cwd': str(tree), 'environment': environment})
        write_json(attempt / 'parent-runtime.json', {'executable': sys.executable, 'version': sys.version,
                   'flags': repr(sys.flags), 'cwd': str(Path.cwd()), 'sqliteVersion': _sqlite3.sqlite_version})
        record['status'] = 'launching'
        with (attempt / 'output.log').open('xb') as log:
            child_deadline = time.monotonic() + args.timeout_seconds
            process = subprocess.Popen(command, cwd=tree, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            # Keep direct-child ownership before any fallible receipt write.
            record['childState'] = 'running'
            record['pid'] = process.pid
            write_json(attempt / 'owned-child.json', {'pid': process.pid, 'ownedByThisAttempt': True})
            record['status'] = 'running'
            record['retainedLogBytes'] = collect(process, log, child_deadline)
            record['exitCode'] = process.returncode
    except BaseException as exc:
        record['status'] = 'timed_out' if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else 'failed'
        record['errors'].append({'phase': 'execution', 'type': type(exc).__name__, 'message': str(exc)[:4096]})
        try:
            (attempt / 'runner-error.txt').write_text(traceback.format_exc()[-65536:])
        except BaseException:
            pass
    finally:
        def finalize(label, callback):
            try:
                callback()
            except BaseException as exc:
                record['errors'].append({'phase': label, 'type': type(exc).__name__, 'message': str(exc)[:4096]})
        finalize('owned-child-cleanup', lambda: stop_owned(process, record))
        if process is not None and process.stdout is not None:
            finalize('pipe-close', process.stdout.close)
        def sources_after():
            if before is not None:
                after = inventory(tree)
                write_json(attempt / 'inputs-after.json', after)
                record['inputsUnchanged'] = before == after
            if frozen_before is not None:
                after = frozen_inputs(stage)
                write_json(attempt / 'frozen-after.json', after)
                record['frozenPreparationUnchanged'] = frozen_before == after
            if own_before is not None:
                after = [row(here / name, name) for name in OWN_FILES]
                write_json(attempt / 'harness-after.json', after)
                record['harnessUnchanged'] = own_before == after
                record['retainedHarnessUnchanged'] = own_before == [row(attempt / 'harness' / name, name) for name in OWN_FILES]
        def external_after():
            if external_before is not None:
                after = selected_external(read_json(attempt / 'harness/references/approved-external-roots.json'))
                write_json(attempt / 'external-after.json', after)
                record['externalInputsUnchanged'] = external_before == after
                record['externalInputCount'] = len(external_before['files'])
        def retain_scratch():
            if scratch is None:
                return
            actual = scratch_identity(scratch)
            parent_actual = scratch_identity(scratch.parent)
            record['rawScratchRetained'] = True
            record['rawScratchIdentityUnchanged'] = actual == scratch_before
            record['rawScratchParentIdentityUnchanged'] = parent_actual == scratch_parent_before
            record['rawScratchInventoryTerminal'] = record['childState'] in {'exited', 'not_started'}
            write_json(attempt / 'raw-scratch-after.json', {
                'identity': actual, 'before': scratch_before, 'parent': parent_actual,
                'parentBefore': scratch_parent_before, 'childState': record['childState'],
                'retentionPolicy': record['rawScratchPolicy']})
            if actual != scratch_before or parent_actual != scratch_parent_before:
                raise RuntimeError('Raw scratch or ancestor identity changed; refuse replacement inventory')
            if not record['rawScratchInventoryTerminal']:
                raise RuntimeError('Original scratch retained; producer termination is unconfirmed')
            rows = inventory(scratch, max_bytes=MAX_SCRATCH_BYTES)
            shutil.copytree(scratch, attempt / 'scratch')
            if (inventory(attempt / 'scratch', max_bytes=MAX_SCRATCH_BYTES) != rows or
                    inventory(scratch, max_bytes=MAX_SCRATCH_BYTES) != rows or
                    scratch_identity(scratch) != scratch_before or
                    scratch_identity(scratch.parent) != scratch_parent_before):
                raise RuntimeError('Scratch identity or retained bytes changed during collection')
            write_json(attempt / 'scratch-index.json', rows)
            record['scratchRetained'] = True
            record['scratchRetainedBytes'] = sum(value['bytes'] for value in rows)
            record['rawScratchMayContainUnsettledFixtureWork'] = bool(rows)
            record['rawScratchCopyVerified'] = True
            # Keep the original root even after a complete copy, including on
            # failed tests/capture/close. This is not a claim of resolved work.
        def child_receipts():
            record['counts'] = read_json(attempt / 'test-return.json')
            record['actualTests'] = read_json(attempt / 'actual-tests.json')
            record['originSummary'] = read_json(attempt / 'imports.json')['summary']
            record['childErrors'] = read_json(attempt / 'child-errors.json')
            left = read_json(attempt / 'compiler-before.json')
            right = read_json(attempt / 'compiler-after.json')
            record['compilerIdentityUnchanged'] = left == right
            record['driverIdentityUnchanged'] = read_json(attempt / 'driver-before.json') == read_json(attempt / 'driver-after.json')
        for label, callback in [('sources-after', sources_after), ('external-after', external_after),
                                ('scratch-retention', retain_scratch), ('child-receipts', child_receipts)]:
            finalize(label, callback)
        flags = ('inputsUnchanged', 'frozenPreparationUnchanged', 'harnessUnchanged',
                 'retainedHarnessUnchanged', 'externalInputsUnchanged', 'compilerIdentityUnchanged', 'driverIdentityUnchanged',
                 'scratchRetained', 'rawScratchRetained', 'rawScratchIdentityUnchanged',
                 'rawScratchParentIdentityUnchanged', 'rawScratchInventoryTerminal', 'rawScratchCopyVerified')
        record['currentPass'] = (record['exitCode'] == 0 and record['childState'] == 'exited' and
            not record['errors'] and counts_pass(record['counts']) and not record.get('childErrors', [1]) and
            all(record.get(flag) is True for flag in flags) and
            record.get('originSummary', {}).get('allOriginsMatched') is True and
            record.get('actualTests', {}).get('exactSelection') is True)
        if record['currentPass']:
            record['status'] = 'passed'
        elif record['status'] in {'preparing', 'launching', 'running'}:
            record['status'] = 'failed'
        record['elapsedSeconds'] = time.monotonic() - started
        try:
            write_json(attempt / 'result.json', record)
        except BaseException as exc:
            record['currentPass'] = False
            print('Final result write failed:', type(exc).__name__, str(exc), file=sys.stderr)
        print(json.dumps({key: record[key] for key in ('attempt', 'status', 'currentPass', 'counts', 'errors')}, indent=2))
    return 0 if record['currentPass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
