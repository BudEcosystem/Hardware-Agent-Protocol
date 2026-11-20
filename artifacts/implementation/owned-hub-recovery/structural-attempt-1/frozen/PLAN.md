# Source review before execution

No candidate worker, control or runner has been executed. Root must review the production/control diffs, fixed CPU diagnostic fixture and bounded runner before any run. All attempts use a new name and preserve frozen inputs and output. Stop after the first failure.

```
python3 -I -S -B run_controls.py structural structural-attempt-1
python3 -I -S -B run_controls.py live live-attempt-1
python3 -I -S -B run_controls.py faults faults-attempt-1
python3 -I -S -B run_controls.py recovery recovery-attempt-1
python3 -I -S -B run_controls.py limits limits-attempt-1
```

The first three groups retain the original finite controls against the changed provider. `recovery` adds one terminal-reconcile case and32 storage/reap combinations. `limits` adds bootstrap, post-release wall and hard CPU controls plus16 actual finite jobs, retention refusal and historical replay. Counts of polling assertions remain timing-dependent. Store per-case observations with the new control groups for independent retained-state review.

The runner retains per-process control ceilings of CPU30s, address512MiB, file1MiB, open-FD128 and no core. Structural/live/fault/recovery/limit group wall observations are15/30/40/40/30s. On an interrupted or overdue control, send anchored TERM and allow8s for its exception/finally cleanup, then anchored KILL if needed and3s exit observation. Hold the unreaped original control anchor through all numeric group signals. The provider's own typed limits remain stricter per-process limits; no aggregate CPU/address-space/storage reservation is claimed.

Before/after every group, verify the existing244-file public receipt/hash set, the complete sealed218-file parent packet, exact baseline source copies and interpreter identity. Frozen per-attempt copies include parent pins, source diffs and change pins. The prior866-test suite is not rerun by these commands. Hash observations are sequential, not atomic snapshots or transient-change detection.

Storage controls inject exceptions at named operations without mounting filesystems, filling disks, changing services or killing the provider owner. Actual power-loss durability, aggregate admission, early-leader-exit and killed-owner recovery remain unqualified. The latter two are explicitly deferred to root's separate owned harness so this increment launches no intentional orphan fixture.
