# Reused controlled runner

The parent runner SHA256 is `a3d6317bb0a4fe39eb884c9654dc558505b61b99ddda57b9f2ced4faaa2d7099`, retained in the sealed standing-controller packet. This candidate changes one line: required standing native cases become 13 instead of 12. [runner-diff.patch](runner-diff.patch) records that exact delta. Commands, flags, target limits, resource/ownership handling, pinning, source snapshots and cleanup are unchanged.

The four owner inputs and their source pins are exact copies. The prior [complete runner review](../standing-endpoint-controller/RUNNER-REVIEW.md) remains the implementation basis: a live sole-thread Linux/x86-64 CPython3.12 subreaper, raw SIGCHLD ownership preconditions, masked orderly INT/TERM ownership/cleanup/publication, retained intent/start/result records, exact selected executable/input checks and bounded per-command limits. Native headers/libraries/loader/stdlib remain trusted unpinned dependencies; RSS observation is not a cgroup containment guarantee. Runner SIGKILL and host death are outside that orderly-cleanup scope.

This new lane has not imported the owner module or run the runner, compilers, native probes or target. Root must read the source delta and this one-line runner change before execution. Subsequent attempt receipts, not copied parent successes, will determine this candidate's result.
