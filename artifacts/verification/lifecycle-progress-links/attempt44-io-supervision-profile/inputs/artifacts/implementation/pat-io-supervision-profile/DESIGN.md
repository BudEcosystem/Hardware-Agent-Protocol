# Diagnostic parent profile

The exact previously failed PWM test runs once in a fresh isolated diagnostic
fixture with its original request, program, worker and supervisor source. Its old
ledger and outputs remain untouched. This does not retry a mutation in the failed
ledger or replace the negative result. A cProfile wrapper around the test records
bounded top-100 parent cumulative/self times, parent CPU and reaped-child CPU.
No binary profile or unbounded function dump is emitted. The profile adds overhead
and cannot establish a deployment benchmark or turn missing evidence into success.

The source remains the sealed 239-file recovery project. Child startup, exact
entry audit, pre-launch inputs, owner/writer lease checks, 60 s supervisor/group,
180 s test-parent, 256 MiB collection, 8192-file, 16 MiB single-file, 4 MiB receipt,
8 MiB log and all effect limits remain unchanged. Originals and incomplete state
are retained. No physical device, MCU, inference or acquired controller executes.
Parent review releases this diagnostic only. Measurements determine the next
change; no cache or reduced validation frequency is assumed in advance.

The second diagnostic instruments only run_io_group in a fresh copy of the
original worker entry. All other 238 project files and the selected test remain
unchanged. Its source identity explicitly includes the instrumentation. It retains
at most 40 cumulative and 40 self-time rows in a canonical, private, fsynced file
bounded by the original 65536-byte writer. It attempts that receipt on SIGTERM,
then re-raises SIGTERM to itself with the default disposition; the supervisor's
original 1000 ms grace and SIGKILL remain available. It never intercepts SIGKILL,
changes an operation budget, or converts interruption into a passing result.
An incomplete profile or transaction remains retained and nonpassing. Parent and
worker instrumentation are separate diagnostic runs, not a controlled benchmark.
