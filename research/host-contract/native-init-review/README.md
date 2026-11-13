# Native interpreter lifecycle review

The retained [CPython v3.12.3 initialization and threads document](init.rst)
is fully read: 2,191 LF lines, adding 2,112 previously unread lines. The six-source
native binding packet now has complete 5,360/5,360-line coverage. The
[reading receipt](reading.json) records seven observed segments and exact hashes;
the [previous receipt](previous-reading.json) preserves the earlier coverage.
This is a reading overlay on the retained release, not a current-version review.
Linked references remain outside the coverage and no acquired example was run.

Embedding configuration belongs to trusted installation. The document describes
`PyConfig` replacements for many deprecated global flags and setters. Isolated
mode removes implicit script-directory and user-site paths; explicit fixed paths
still need their own source inventory. The older argument setter can prepend a
script directory or the current directory. HMS's namespace and protected worker
image are consistent with making that choice explicit; isolation flags alone do
not authenticate code or provide an operating-system sandbox.

Interpreter destruction is not a driver unload receipt. Finalization may flush
streams with an error, destroys objects in an unspecified order, and does not
unload dynamic extension modules. Reinitializing an extension can also fail.
For an HMS driver or intelligence hub service, stop admission, callback draining,
thread completion, descriptor ownership and durable effect reconciliation need
their own contracts before a lifecycle operation can report completion.

Releasing the GIL permits other Python threads to proceed, but native work must
avoid Python objects until the GIL and correct thread state are restored. Calls
from foreign threads need an associated interpreter state. The `PyGILState_*`
convenience API assumes the main interpreter and is unsuitable as a general
subinterpreter dispatch mechanism. Several GIL acquisition functions in this
retained release may terminate a thread during runtime finalization. These are
additional reasons to drain callbacks before destroying an embedded runtime.

The later subinterpreter section describes an optional per-interpreter GIL and
its allocator/extension compatibility constraints. Earlier general wording says
the GIL is shared; that wording must be read with the later explicit configuration
options. Separate module dictionaries and even separate GILs do not isolate
process descriptors, memory exhaustion, crashes or mutable C globals. The retained
example for `Py_NewInterpreterFromConfig` also uses a one-argument, pointer-return
form inconsistent with the two-argument `PyStatus` signature immediately above
it. It is retained as conflicting source evidence, not copied into HMS code.
Any future embedding implementation must check the actual pinned headers and
implementation and compile its own call site.

Pending calls are queued notifications with no prompt-execution guarantee; a
blocking system call can delay them. Asynchronous exception injection similarly
does not supply device quiescence or a hard stop deadline. Forking a multithreaded
embedded process can strand locks whose owning threads disappear; Python cannot
repair arbitrary third-party locks. A process/driver profile needs a deliberate
launch and shutdown strategy. This reading establishes neither physical stop
behavior nor a measured bound.

Tracing and profiling callbacks differ in the events they report; neither is a
complete I/O effect ledger. Thread-specific storage requires explicit key and
value ownership, and does not manage Python reference counts. These facilities
can support diagnostics, but should not become authority, replay or cancellation
evidence by themselves.
