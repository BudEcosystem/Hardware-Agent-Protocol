# Current worker deadline diagnosis

The sealed [recorded catalog stage](../pat-io-recorded-catalog/README.md) has 19 passing fixture controls and two failed actual process scopes. The earlier actual worker completed all 30 cases; the corrected process test stopped during case-16 at the unchanged 60-second supervisor deadline. Existing phase timestamps do not identify the cause. The old worker profile predates normalization and canonical-document reuse, so its function costs cannot be treated as current measurements.

One fresh diagnostic uses the exact current process test and changes only the fixed worker entry. It reuses the previously reviewed bounded cProfile wrapper: the full matrix executes under the original limits, with at most 40 cumulative and 40 self-time function records. A SIGTERM handler writes the bounded profile, restores the default signal disposition and re-raises the signal. The original supervisor termination/grace rules remain. This handler is diagnostic only and must not enter production.

No old logical run or failed state is reused. The original 60-second worker/group, 180-second parent, matrix coverage, persistence and effect/storage limits remain. Partial states and any diagnostic failure are retained. Profiling adds overhead; a profile does not prove the cause of the previous timeout or production timing. Follow-up changes require a concrete supported mechanism, not weaker validation, fewer cases or relaxed writes.

The full HMS objective remains active, including prompt-to-PAT learning, device I/O and drivers, persistent microcontroller applications, intelligence-hub resources, public Harness integration and physical qualification.
