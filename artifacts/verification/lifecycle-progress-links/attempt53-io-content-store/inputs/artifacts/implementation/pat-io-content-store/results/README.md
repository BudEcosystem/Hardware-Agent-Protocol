# Completed compact-store results

All 19 scopes pass with exact one-method receipts, zero failures/errors/skips, unchanged inputs and complete scratch retention. Eighteen controls use explicitly substituted workers/semantic results. One process scope executes the actual complete 30-case simulation and original-run import/replay. These results do not constitute a rerun of the earlier full runtime regression.

| Scope | Evidence | Method | Result |
| --- | --- | --- | --- |
| [harness01](../harness01/attempts/attempt01/result.json) | Fixture control | `test_exact_reconstruction_deduplicates_without_dropping_references` | Passed |
| [harness02](../harness02/attempts/attempt01-compact-real/result.json) | Actual 30-case worker | `test_compact_bound_worker_import_and_historical_replay` | Passed |
| [harness03](../harness03/attempts/attempt01/result.json) | Fixture control | `test_authorization_is_rechecked_after_compact_inspection` | Passed |
| [harness04](../harness04/attempts/attempt01/result.json) | Fixture control | `test_corrupt_shared_body_refuses_fresh_reuse_without_repair` | Passed |
| [harness05](../harness05/attempts/attempt01/result.json) | Fixture control | `test_creation_limits_never_widen_and_reopen_options_refuse` | Passed |
| [harness06](../harness06/attempts/attempt01/result.json) | Fixture control | `test_extra_body_index_is_retained_and_refused` | Passed |
| [harness07](../harness07/attempts/attempt01/result.json) | Fixture control | `test_invalid_body_type_refuses_before_fetching_payloads` | Passed |
| [harness08](../harness08/attempts/attempt01/result.json) | Fixture control | `test_legacy_mount_and_identity_remain_separate_and_usable` | Passed |
| [harness09](../harness09/attempts/attempt01/result.json) | Fixture control | `test_lost_reply_replays_original_without_duplicate_bodies` | Passed |
| [harness10](../harness10/attempts/attempt01/result.json) | Fixture control | `test_lower_expanded_quota_is_not_bypassed_by_deduplication` | Passed |
| [harness11](../harness11/attempts/attempt01/result.json) | Fixture control | `test_lower_object_quota_refuses_atomic_publication` | Passed |
| [harness12](../harness12/attempts/attempt01/result.json) | Fixture control | `test_missing_body_refuses_without_reconstructing_worker_output` | Passed |
| [harness13](../harness13/attempts/attempt01/result.json) | Fixture control | `test_missing_body_table_with_anchor_is_not_reinitialized` | Passed |
| [harness14](../harness14/attempts/attempt01/result.json) | Fixture control | `test_orphan_body_is_retained_and_refused` | Passed |
| [harness15](../harness15/attempts/attempt01/result.json) | Fixture control | `test_rehashed_cross_run_reference_still_refuses_authority_mismatch` | Passed |
| [harness16](../harness16/attempts/attempt01/result.json) | Fixture control | `test_reinspection_uses_reconstructed_bytes_outside_journal_transaction` | Passed |
| [harness17](../harness17/attempts/attempt01/result.json) | Fixture control | `test_rollback_publishes_no_objects_references_or_receipt` | Passed |
| [harness18](../harness18/attempts/attempt01/result.json) | Fixture control | `test_temporary_body_shadow_is_refused` | Passed |
| [harness19](../harness19/attempts/attempt01/result.json) | Fixture control | `test_two_runs_share_exact_bodies_and_keep_distinct_receipts` | Passed |

The actual integration retains all 4,256 scratch files. Its authority database is 16,132,096 bytes, leaving 645,120 bytes under the original 16,777,216-byte single-file limit. All 4,011 evidence references remain, backed by 2,798 exact bodies. The audit verifies original supervisor/authority/handoff associations, complete simulation inspection, and historical replay after configuration and session changes.

See the [aggregate audit](../RESULTS.json), [actual-data audit](../actual-import-audit.json), [review](../REVIEW.md), and [next work](../NEXT.md). Earlier failures remain immutable. Public PAT eligibility, physical qualification and a general capacity/timing guarantee remain unclaimed; the full goal is active.
