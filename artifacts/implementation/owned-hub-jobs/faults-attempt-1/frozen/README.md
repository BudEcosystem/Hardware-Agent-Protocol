# Owned host CPU-job candidate

This isolated source candidate adds typed `start`, `lookup`, `poll`, `cancel` and `reconcile` operations for one installed arithmetic CPU artifact. `start` returns a real associated child behind a closed gate; first poll releases it. Original keys retain exact replay/conflict behavior. A pidfd and an unreaped owned leader govern live control; persisted PIDs never grant signal authority. Successful output requires exact association, strict typed arithmetic validation, exit, observed group quiescence, EOF and the matching inherited writer lease.

The implementation is under `project/owned_hub_jobs/`. Read [DESIGN.md](DESIGN.md) for contracts and original HMS source mapping, and [PLAN.md](PLAN.md) for the review-gated bounded control slice and unimplemented qualification. Host-job controls remain unexecuted. Only the root's original SIGCHLD helper control in `helper-check01` has been run and is preserved.

This is a real host-effect component candidate, separate from public simulation. It does not claim sandboxing, universal process containment, aggregate capacity, qualified control storage, actual killed-owner crash recovery, hub GPU readiness, driver/device control or learned PAT installation. Those remain integration and qualification work.
