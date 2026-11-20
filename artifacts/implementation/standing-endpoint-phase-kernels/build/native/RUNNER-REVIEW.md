# Runner delta prepared for root review

runner-baseline.py is the exact sealed shared-kernel runner. runner-diff.patch is the complete source delta; no runner was imported or executed during preparation. The owner, signal, process launch/registration, anchored cleanup, pidfd/subreaper settlement, durable per-command receipts, executable/open-fd pins, source/tool/runtime rechecks and terminal-failure publication code remain unchanged.

Changes are limited to backend/source/control selection and input coverage:

1. Add BYTE_FLAGS selecting HMS_EP_BYTE_BACKEND=1 to regular native runtime/standing and AVR compile/link paths. The copied original-native script has one corresponding COMMON flag insertion so finite/pipe checks exercise byte code too.
2. Preserve the unchanged 14 standing bodies, and add five source-span/hash checks for the original three numeric and two finite differential functions. All original files are frozen, not just the prior predecessor subset.
3. Run the six numeric groups with backend1 and backend0 in each native mode. Verify explicit backend, old-group count, greater-than-parent observed assertion coverage, and equality apart from backend identity. Record actual assertions.
4. Compile three complete controller traces per mode: unchanged parent scalar, candidate byte and candidate fallback. Every one links the selected endpoint_kernel.c. Native-only phase_access.c includes selected standing.c, so the standalone standing object is omitted only in these trace builds. Require identical full output and 20 groups with retained old14/766 and prior added475 coverage. Compare plain and sanitized traces too.
5. Freeze this lane's metadata, all originals and all immutable staged history. Keep stage/attempt creation refusals and source snapshots before any child launch. Update the pending generated review label; retain no-fit/no-final-stack defaults.

The inherited per-command bounds remain 60s wall, 30s CPU, 64MiB file, 64 descriptors, no core dumps, 512MiB non-ASan address space and observed group RSS ceiling. Anchored group cleanup retains its 3s bound and adopted-child cleanup 8s. Native trusted headers/libraries/stdlib/loader remain outside a complete pinned dependency closure. Orderly INT/TERM cleanup is covered by source protocol; runner SIGKILL/host failure, cgroup containment and hostile-process isolation are not claimed.

No new process capability, package, device access, shell command execution path, toolchain download or inspection command is added. The normal fixed AVR queries and compile/link/disassembly commands remain gated on root execution review. All failure artifacts and logs must remain in their original attempt. Root will review this exact delta and frozen pins before invocation; a historical parent pass does not qualify this new source.
