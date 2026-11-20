# Standing host owner-death qualification design

This is a source-only plan for thirteen fixed process-death checkpoints against
the existing synthetic native standing endpoint. No candidate import, build,
test, child process, signal, device or network operation was performed to produce
these notes. Host source was read during review and joined to the preserved
revision04 source manifest; the subsequent revision05 patch was also read. No
host source was copied or frozen by this design.

[PLAN.md](PLAN.md) defines the process and descriptor ownership, exact cut points,
expected recovery classifications, evidence and bounds. [SOURCE-COVERAGE.json](SOURCE-COVERAGE.json)
records full-file and selected-range reads separately. Existing successful CPU-job
owner-death evidence supplies an ownership model, not evidence that these standing
host cases have passed.

Implementation must wait for an exact reviewed host revision and original native
qualification bundle. Any intervening host correction requires a new source join
and review of affected expectations. The plan deliberately keeps the native peer
alive when its host owner dies and preserves unknown effects without resending.
It does not qualify partial-frame deaths, mid-transaction rollback, host power
loss, physical I/O, protected capacity or loss of the surviving guardian.
