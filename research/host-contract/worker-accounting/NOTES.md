# Reading notes and design consequences

## Linux resource usage

The [getrusage manual](https://man7.org/linux/man-pages/man2/getrusage.2.html)
documents user/system CPU time and cumulative resource counters. `RUSAGE_SELF`
includes the process's threads. `RUSAGE_CHILDREN` includes terminated, waited-for
children and, conditionally, their waited-for descendants. An interval needs
explicit launch and reap association before attribution. Linux `ru_maxrss` is
KiB; for children it is the largest child's peak, not the total of peaks. It is
not an additive counter. Filesystem input/output and context-switch fields count
events, not transferred bytes or waiting duration. Several historical fields are
unmaintained on Linux; zero does not establish measured absence.

The retained page identifies Linux man-pages 6.19. Its complete 207-line extracted
manual, headings and surrounding navigation were read. Linked manuals remain
separate. HMS should retain raw snapshots, derive only documented additive
deltas, and leave incomplete child intervals unavailable.

## Python interface

The [Python 3.12 resource reference](https://docs.python.org/3.12/library/resource.html)
exposes Unix resource accounting and platform-dependent limits. `getrusage`
returns named fields; user and system times are floating-point seconds. Resource
limits and their availability vary by operating system. Reading accounting does
not require modifying limits. The complete retained 385-line source was read,
including limits, selectors, exceptions, usage fields and examples. No examples
were executed. The documentation branch alone does not attest the installed
interpreter's precise patch version.

HMS will preserve the interpreter version and units in the diagnostic receipt.
No affinity, priority, resource-limit or service changes belong in this observer.
CPU time summed across threads can exceed elapsed time; no CPU-to-wall assertion
should assume one runnable thread.

## Pressure stall information

The [kernel PSI documentation](https://docs.kernel.org/accounting/psi.html)
describes `some` and `full` pressure, rolling averages and cumulative microsecond
totals. Global files aggregate system contention; they do not attribute a stall
to the owned worker. System-level CPU `full` is undefined and exposed as zero
for compatibility. Trigger registration writes to a pressure descriptor and is
unnecessary for this diagnostic. The complete 188-line retained source was read,
including the trigger example, without executing it.

HMS will retain bounded read-only global snapshots, explicitly labelled as host
context. Missing files, permission errors and malformed text remain unavailable
observations. No pressure value by itself proves why a particular worker missed
its deadline.

## Scheduler statistics

The [kernel scheduler statistics](https://docs.kernel.org/scheduler/sched-stats.html)
describe versioned, cumulative CPU/domain counters and task scheduling data.
Format changes matter when computing deltas. The complete retained 205-line
source was read. Its wording about `/proc/<pid>/schedstat` is insufficient here
to establish aggregation across all process threads or behavior when accounting
is disabled. A primary kernel patch about misleading per-process wording was
found in search but has not been acquired or read; it supplies no evidence yet.

HMS will defer task scheduler counters until kernel implementation, version and
configuration semantics are reviewed. A leader's counter must not silently
become a whole-worker waiting measurement. Nothing will enable scheduler
accounting or change its settings.

## Process stat identity and counters

The [proc_pid_stat manual](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)
defines process fields and units. Parenthesized command names complicate parsing.
CPU and process-start fields use clock ticks; field 42 has separately documented
units. Some permission-controlled fields may appear as zero. RSS is described as
inaccurate. The complete retained 330-line manual, headings and surrounding
navigation were read; it identifies Linux man-pages 6.19.

HMS must not infer signal authority from a PID or treat a recycled PID as the
original child. The initial observer needs no PID-based counter reads: it uses
the object returned by the sole permitted launch and records the inherited
attempt-directory and writer-lease identities while their descriptors are live.
Any later `/proc` sampling requires separate ownership and race analysis.

## Initial measurement boundary

Measure once before and after the selected test, and immediately before the
original child launch and after its existing poll/wait first reports termination.
These nested intervals separate whole-test parent work from parent work while
the child is outstanding. They do not identify individual function costs or
precise blocking causes. There must be exactly one permitted child launch, with
unchanged project and producer-image bytes. Retain partial observations even if
the integration fails. Measurement success cannot turn an incomplete original
worker, import or PAT application into a passing qualification.

Further reading remains: linked manuals, cgroup-v2 accounting, actual kernel
scheduler implementation/configuration, and the referenced scheduler wording
patch. Wider protocol and physical-device research is also incomplete.
