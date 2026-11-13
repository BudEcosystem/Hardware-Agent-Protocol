# Ownership implications for a hub-job provider

`pidfd_open` supplies a process reference with explicit polling and waiting
semantics. Acquiring it after fork also works for an exited child only under the
documented signal/reaping conditions: no explicit SIGCHLD ignore, no
SA_NOCLDWAIT, and no other code reaping that child first. A `/proc/PID` directory
descriptor is not interchangeable with a pollable/waitable pidfd. **Design
inference:** the provider must own child collection or select a separately
qualified creation mechanism that obtains the pidfd atomically. Merely checking
that Python exposes an API is insufficient to establish those ownership
preconditions. [Primary manual](https://man7.org/linux/man-pages/man2/pidfd_open.2.html).

`pidfd_send_signal` avoids selecting a different process after numeric PID reuse.
Its default scope is not an entire process group. The documented process-group
flag is a newer Linux interface, so choosing it requires an explicit supported
profile and a local capability check. Namespace and permission errors remain
possible. **Design inference:** persisted PIDs provide diagnostic information,
not recovered signaling authority. Unknown ownership must not cause a fresh
launch or a signal to a reconstructed numeric target.
[Primary manual](https://man7.org/linux/man-pages/man2/pidfd_send_signal.2.html).

`waitid` can inspect a child through P_PIDFD and preserve waitability using
WNOWAIT. Normal reaping releases the retained child state. Explicit SIGCHLD
ignore and SA_NOCLDWAIT affect zombie/wait behavior, and another thread may
collect a child. **Design inference:** preserve the owned leader until any
numeric group signaling finishes; do not insert an unnoticed Popen.poll/wait
that reaps it first. Treat ECHILD or ownership inconsistency as a failed
assumption, not evidence that all outputs and descendants are settled. Bound
the retained-child lifecycle so unresolved work does not leak process-table
entries indefinitely. [Primary manual](https://man7.org/linux/man-pages/man2/waitid.2.html).

Process groups belong to sessions. Fork inherits group membership and exec
preserves it, but supported interfaces can alter grouping under their stated
conditions. Grouping also interacts with terminal job control and orphaned
stopped processes. **Design inference:** a session/process group is useful
control structure for a fixed trusted worker contract, but cannot by itself
establish that every descendant remains contained. A writer-lease protocol
requires cooperative inheritance and retention until actual writing ends.
Broader arbitrary-worker containment needs a separate enforced profile.
[Primary manual](https://man7.org/linux/man-pages/man2/getpgrp.2.html).

The public qualification supervisor already holds live Popen/pidfd pairs,
records launch intent, bounds stream capture and checks a writer lease before
archiving. It runs one fixed qualification worker and does not expose concurrent
cancellation while collecting. It can archive retained output separately from
semantic qualification, and does not declare total storage quota enforcement.
These source facts support reuse of reviewed patterns, not reuse of its class
as a general host-job provider. A new provider needs typed installed artifacts,
an explicit launch association, concurrent serviceable cancellation, valid
output checks and its own crash/recovery controls. Public PAT and device policy
must not mislabel real host execution as simulation.
