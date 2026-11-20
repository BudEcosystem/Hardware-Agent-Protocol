# Exact block-read profile regression gate

Stage 87, 2026-11-09. Stage 86 observed real host allocator exhaustion and
independent control writes using its separate block-read evaluation. That native
profile has not passed the complete original regression matrix. Reuse its exact
library, bridge and Python adapter in this separate artifact; do not modify or
repair sealed evidence or install the profile into the public runtime.

Run all six original semantic scopes / 54 checks and all 22 original interruption
cases / 24 selected owner terminations once against the exact evaluation binary.
Freeze the original controls, matrix, case oracles, read-only inspector and all
native/provider dependencies. Keep their current operation/checkpoint/recovery
logic, including pidfd ownership, poison/refusal semantics, expected old/new
outcomes and copy-only recovery. Preserve any failure and stop the matrix.

The profile has 4,096-byte read/cache size, 16-byte programs, 4,096 blocks and a
16 MiB image. Every provider ownership/allocation check remains active. It is an
explicit host profile, not a tiny-MCU memory or real-time timing claim.

Each scope retains 60-second wall / 40-second CPU limits, 512 MiB address space,
128 FDs and 16 MiB per-file limits; selected owners retain 15/10-second limits.
Maximum retained backing is 52 images / 832 MiB; total stage inventory must remain
below 1 GiB. Verify sufficient current disk space before freezing or execution.
No widened limit or automatic retry is permitted. Reinspect the 52 retained
images read-only, join original checkpoint/intent/copy records, and verify all
244 public runtime inputs against the 866-test receipt. Do not rerun that
unchanged public suite or repeat the unchanged capacity experiment.

Passing these selected regressions permits further private host integration
work. It does not qualify every interruption, physical power loss, the actual
SQLite DELETE/EXTRA interface, all-writer confinement, backed continuation
capacity or complete service recovery. Device/driver/hub providers and the
prompt-to-qualified-PAT learning service remain broader required work.
