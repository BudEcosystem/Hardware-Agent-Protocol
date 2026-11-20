# Next work

Preserve the failed original integration and its partial effects. Keep the
proof-build candidate isolated. Do not rerun this same scope hoping for a pass,
increase the 60/180-second limits, shrink the 30-case matrix, relax file/storage/
effect limits, repair partial state, or replace original mutation keys.

The new observation establishes a substantial parent CPU cost while the worker
is outstanding: 18.454471 seconds, compared with 36.580244 child CPU seconds.
It does not establish that parent monitoring caused the deadline. Both include
their existing runtime/harness costs; scheduling and blocking causes remain
unattributed. Twenty-five retained manifests versus nineteen in the preceding
run is not a controlled performance comparison.

Review the exact supervisor collection loop and `tree_usage` before changing it.
The loop scans the growing tree before each selector wait. A bounded, read-only
evaluation on the retained quiescent tree can measure scan cost and test a
semantics-preserving implementation without launching another worker. Hold the
original ownership/writer locks for any such experiment, read directory metadata
only, and do not open interrupted case databases. If the original raw tree has
disappeared, state that explicitly: copied directory metadata is a different
measurement scope and cannot reproduce original inode ownership or timing.

Any proposed correction must preserve no-follow traversal, depth and count
bounds, ownership/mode/link checks, all byte ceilings, races/refusal semantics and
deadline responsiveness. Reducing the frequency of checks is not established as
an equivalent optimization. Admission still lacks a real aggregate quota and
backed control reservation. Additional attribution, if needed, must remain
bounded and avoid per-call worker profiling or changing affinity, priorities,
quotas, services or signal behavior. Cgroup/thread scheduling claims require the
additional primary-source reading identified in the research packet.

Then complete the original authority-vault import and the separate held-snapshot
catalog integration, including validation immediately before business commit.
The [catalog review](../../implementation/pat-vault-original-run/CATALOG-NOTES.md)
records those obligations. Public qualification/PAT mounting, backed control
capacity, natural-language synthesis and learning, persistent Arduino programs,
actual device I/O/driver/hub providers and physical commissioning remain required.
This diagnostic changes none of those completion claims.
