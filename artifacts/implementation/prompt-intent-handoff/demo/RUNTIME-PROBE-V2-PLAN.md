# Public Runtime read-tool demonstration — second source, unexecuted

The first actual attempt failed at Runtime construction with
`UNSAFE_STATE_ANCESTOR`. It made **zero actual read calls**, created no Runtime
object or child, and verified all 244 public inputs unchanged. Its original
`scope.realRuntimeReads: true` is a declared profile flag, not evidence that
reads happened; the empty `readMethods` and initialization failure establish
zero reads. Its complete source, pins, plan and three attempt files remain
unchanged and are pinned by this separate successor.

`runtime_probe_v2.py` has not been imported or executed. The proposed fixed
command is `/usr/bin/python3.12 -I -B artifacts/implementation/prompt-intent-handoff/demo/runtime_probe_v2.py`.
It creates only an exclusive `demo/runtime-probe-attempt02`; there is no automatic
retry, old-state adoption or replacement. Review the exact v1-to-v2 diff before
root execution. All four read calls, public source checks, process/socket
refusals, 30-second CPU/wall, 512-MiB address-space, 1-MiB per-file, FD64, core0
and output limits are unchanged.

The only Runtime-state placement change is `tempfile.mkdtemp` with a fixed
`hms-prompt-runtime-probe02-` prefix under `/tmp`. That creates one fresh,
current-UID-owned 0700 directory below the root-owned sticky ancestor. The
unchanged public state-path validator must accept it independently; no workspace
mode, validator, installation, authority or dependency is modified. The exact
created path, directory inode/device and ownership are recorded before Runtime
construction. The state remains there after process exit and is not reopened as
an authority by this probe. No file or directory is deleted.

After Runtime closes, separate query-only connections check its original
SQLite state for zero operations, claims, procedure work and simulated effects.
The exact four closed ordinary files (two databases and two owner files) are
copied with bounded raw reads into `attempt02/state-snapshot`. Every file must
be owned, mode0600, single-linked and regular; unexpected sidecars or inventory
refuse the copy. Source bytes are rechecked after copying and matched against
the retained bytes, and query-only checks of the copied and original states
must agree. `closedStateCopies` joins the original paths/inodes to retained
paths, lengths and hashes. This copied evidence is not a live Runtime mount or
a substitute authority; the original `/tmp` state is preserved. The small
closed-copy checks exclude hostile same-UID concurrent replacement, as did the
trusted original path. The observed aggregate evidence bound is not protected
storage capacity.

The new receipt reports `actualReadCount` and derives `realRuntimeReads` from
actual successful replies. It separately records the prior failed attempt's
zero-read outcome. The root-authored prompt remains exact: one proposed
37-percent-then-zero routine, with no command execution or standing controller.
No candidate, proposal, model, qualification run or native child is generated.
The full previous source-level limits and dependency exclusions remain in
`RUNTIME-PROBE-PLAN.md`; this file documents the narrow correction and actual
first-attempt outcome only.
