# Retained results

The [aggregate read-only audit](../RESULTS.json) verifies **25 scopes: 19 passed and six failed**. There are 22 complete one-method receipts; one startup failure, one intentional import-only diagnostic and one pre-child refusal have no completed method receipt. Both actual integration scopes remain failed.

| Scope | Result and interpretation |
| --- | --- |
| harness01 / source01 | Startup import failure; no test method, database or worker ran. |
| harness21-import-diagnostic / source01 | Intentional import-only diagnostic retains `ModuleNotFoundError: attempt_ledger`; no method, database or worker ran. |
| harness22 / source02 | Runner refused a stale source-directory literal before child startup. |
| harness42 / source02 | Fixture control errored when the existing SQL guard refused `GLOB`. |
| harness62 / source03 | Original invocation/promotion smoke control passed. All production and control-test bytes are unchanged in source04. |
| harness63 / source03 | Full 30-case worker, import, promotion and one application completed; the test failed on the number of pre-created effect-counter rows. Later replay checks were not reached. |
| harness83 / source04 | Original worker deadline expired; no import/catalog/application followed. Partial worker effects remain unresolved in the archive. |
| harness84–101 / source04 | All remaining 18 fixture controls passed, executed once with at most two scopes in parallel after the failed worker was terminal. |

The [source03 state audit](../source03-actual-state-audit.json) observes one activation and completion, zero cancellation, no held claims/board ownership and the exact original import/catalog association. The [source04 deadline audit](../source04-deadline-audit.json) establishes writer quiescence without claiming zero partial worker effects. The original conservative unsettled-state flags remain unchanged.

All frozen inputs and original/copied scratch files matched. The aggregate audit reacquired 167 original owner/writer locks and inspected 66 parent database records through immutable read-only connections, preserving every database hash. It validates the saved results; it does not rerun test methods or qualification workers.

Unused frozen harnesses remain unexecuted. `run-controls-source03.py`, `run-controls-source04.py` and `audit-actual.py` are retained, unexecuted proposals whose prerequisites were not met. The executed control launcher is `run-controls-after-deadline.py`. No actual end-to-end pass, physical qualification, public catalog mounting or general timing/capacity guarantee is claimed.
