# Authority-bound vault import: implemented candidate, verification incomplete

The new importer binds an independent evidence vault to an actual synthetic
runtime authority through an administrator-owned installation. It records the
original evaluator/run import intent before archive access, uses the existing
archive reader and semantic reducer, seals immutable evidence independently, then
publishes a reference while holding a current checked vault snapshot. No import
path launches another qualification worker. See [design](DESIGN.md).

All 280 inherited project files remain unchanged. Three new production modules
and one test module were added. The [current source](implementation02/README.md)
corrects one error-propagation defect in the new importer; the standalone vault,
legacy consumer, catalog, execution store and Journal remain unchanged.

## What is verified

The [executed progress audit](PROGRESS-RESULTS.json) records:

- **Source01:** eleven methods have passing receipts, including real authority
  installation, original publication and cold replay, durable intent/seal
  reconciliation, rollback, lost replies, expiry and original-attempt changes.
- **Source02:** three focused controls pass: configuration change after sealing,
  permission revocation after sealing, and snapshot-expiry rollback. The original
  nineteen methods are unchanged and one post-seal revocation method was added.
  **Seventeen current-source methods still require verification.**
- An independent read-only audit checks fifteen databases under twenty owner
  locks. It recomputes source identities, installation/intent/manifest bindings,
  all selected body hashes and closures, and an original published reference.
  Every audited database remains byte-identical. Both the failed configuration
  fixture and its corrected successor retain one intent and one manifest with
  zero publications.

These controls use a declared substitute semantic oracle. No actual worker or
physical device executes. The new profile has not yet imported the actual
retained 30-case evidence dataset, entered the catalog or been publicly mounted.
Logical intent charges reserve no physical filesystem capacity.

## Retained failures and performance limits

| Scope | Retained result | Meaning |
|---|---|---|
| harness01 | Ten setup errors; zero SQLite opens | Runtime correctly refused group-writable workspace ancestors |
| harness03 | Ten setup errors; twenty runtime SQLite opens | Harness mishandled directory-relative file opens; no test body entered |
| harness05 | SIGKILL after five logged successes, during method six | Aggregate failed; final count/origin receipts missing; no full pass claim |
| harness07 | One diagnostic error during installation | Instrumentation reached snapshot expiry; it never measured import/reconciliation |
| harness13 | One pass, one assertion failure | Configuration refusal was incorrectly normalized to a generic vault error |

The corrected importer lets the vault finish its normal snapshot checks and
cleanup, then re-raises the original authority refusal. Vault expiry or cleanup
failure still takes precedence. The failed configuration fixture is unchanged.

The passing small scopes do not pass the failed aggregate timing scope. Parent
180-second, child 120-CPU-second, five-second snapshot, file, scratch, output and
connection limits were not widened. The [diagnostic profile](profile-findings.json)
primarily measured fixture preparation under instrumentation; it is not a
deployment-latency measurement.

The prepared source01 harness02/04/06/14–17 were not executed and are superseded.
The original full-selection audit draft `audit-results.py` was never executed;
only [audit-progress.py](audit-progress.py) supplies the current audit receipt.

[Next work](NEXT.md) lists current-source coverage, actual-original-run validation,
catalog integration, protected control capacity and the remaining full HMS goal.
