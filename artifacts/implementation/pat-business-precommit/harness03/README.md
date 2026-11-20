# Bounded host transaction controls

One owned isolated Python child runs exactly 29 new methods and 22 unchanged
Journal methods selected by [the frozen list](../implementation03/test-selection.json).
The two existing process-crash/recovery methods are not run here. All legacy
temporary directories are retained by a test-fixture override; source methods
remain unchanged. Five new methods use actual small vault snapshots whose
manifests claim only immutable fixture bytes. No qualification worker is launched.

The child has 45 CPU seconds, 512 MiB address space, 8 MiB per file and 128 file
descriptors. The parent permits 60 wall seconds and reaps its one owned child.
Python audit controls refuse child processes, network, device-file access and
writes/database opens outside the fresh attempt. Project and selected dependency
sources are hashed, normally imported and checked again afterward; project and
dependency bytecode is refused. Interpreter and standard-library runtime are the
installed environment, not a fully attested dynamic-library closure.

The parent retains stdout, stderr, receipts, all created test databases and their
owner files. It verifies input stability and indexes the retained files. New test
observations include final row counts, clock floor and SQL traces. The SQL guard
is exercised by real statements; callback fault injection is synthetic installed
test code. No public runtime, physical device, hub service or Arduino program is
changed. The next catalog mount must still connect the new commit check to a
complete bounded evidence view and current authority/applicability checks.

The first harness omitted the pinned supervisor module search directory. Its
terminal failure and every retained fixture remain under harness01; no passing
count is claimed for that attempt. This correction adds that exact source root
and retains the unittest log before post-run identity verification. Production
and tests remain byte-for-byte unchanged.

Source03 adds shared reentry ownership with the existing catalog evidence guard.
This harness runs all 51 controls after that production change. The preceding
50-test passing result remains evidence for source02 only.
