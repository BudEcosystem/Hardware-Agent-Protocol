# Current worker profile

The bounded diagnostic captured a profile before the unchanged supervisor deadline terminated the worker. The original test remains **failed**. It requested all 30 cases and retained 23 case directories, 22 manifests and all partial states. No evidence import, catalog evaluation or source application followed.

The [read-only audit](RESULTS.json) verifies the frozen source/harness, acquired origins, all 2,956 original/copied scratch files and original database bytes. It reacquires all original owner/writer locks. The archive's unresolved-effects field remains unknown; quiescence does not establish successful qualification.

The instrumented group recorded 57.901 seconds wall time and 40.832 seconds process CPU time. It observed 102,096 SQLite calls, 2,568 fsync calls and 28,060 canonicalization calls. These counts and overlapping function times describe this interrupted, instrumented run; they do not establish the cause of the previous uninstrumented timeout or deployment performance.

One concrete duplication is supported by both profile and source: `definitions` ran 90 times, with 6.055 seconds cumulative profiled time. For the usual one-action instance, it derives a complete static resource proof inside `handler_details`, then derives it again when constructing the same instance binding. Neither calculation reads current authority or device state. A local refactor can derive one proof per instance within the same pure build call, preserving the public handler function's fresh-proof behavior and all live checks.

See the [design](DESIGN.md), [instrumentation patch](worker-instrumentation.patch), [source review](implementation01/source-review.json) and [exact harness](harness01/SCOPE.md). The diagnostic SIGTERM handler must not enter production. The full HMS goal remains active.
