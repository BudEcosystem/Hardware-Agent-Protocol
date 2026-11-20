# Qualification libraries in the main project

The missing **82 library files are installed byte-for-byte** from the sealed
candidate: 40 finite-I/O host modules and 42 qualification-package files. All 43
existing host modules and seven schema files remain unchanged. No public Runtime,
CLI or MCP method is added, and no qualification service starts automatically.
[Installed library guide](../../../docs/qualification-libraries.md).

The [installed import inspection](inspection01.json) exactly matches the qualified
candidate's identity report: 39 origins, 17 poisoned legacy module names, four
initializer-drift refusals and 267 producer-image files. It forbids database,
process, network, native-load and file-write effects. The native profile remains
Linux/CPython 3.12/x86-64 with its exact binary hash; no target or ABI is newly
qualified. [Selection](selected-source.json), [source review](source-review.json),
[inspection adaptation](inspection.patch).

Five original held-vault commit checks join the public suite with their class AST
unchanged. Their imported table contract and base methods are checked; only the
existing public fixture's isolated workspace setup differs from the retained
harness. Explicit selection avoids rerunning inherited Journal checks. Dedicated
worker/process/crash suites remain in their original bounded scopes. The complete
thirty-case worker from the previous stage is not repeated for this byte-exact
installation.

The runtime receipt runner now captures qualification Python modules, C source
and the native binary. Its only code change is the three inventory patterns in
the [runner diff](runtime-runner.patch). The frozen public inventory contains
**244 inputs**: the prior 161 paths plus 82 library files and one test module.
Only the receipt runner changed among the old paths. [Frozen inputs](inputs.json).
The full regression passes **866 distinct tests** with no failures or skips,
preserving all 861 prior identities and their relative order. Every one of the
244 inputs remains stable. [Runtime audit](RUNTIME_RESULTS.json) verifies input
snapshots, output hashes, exact added test identities and installed source.

The [plan](PLAN.md) preserves the complete user goal. Public qualification still
needs enforceable storage and recovery guarantees; prompt learning, persistent
MCU applications, actual device/driver/hub providers, Harness installation,
microscope commissioning and broader research/scenario work remain unfinished.
[Next work](NEXT.md). No physical device, live inference or new qualification
worker is executed by this installation step.
