# Pre-execution review

Primary-agent review only. Full source reading confirms that file flush copies
the unchanged suffix, that separate handles retain CTZ/cache state, and that
unmount releases buffers without synchronizing open files. The probe records
these outcomes; it does not weaken a production contract to accept them.

The adapter is original and RAM-only. All callbacks reject range/alignment
violations before memory access; programming also checks erased bits. Caller-owned
buffers and LFS_NO_MALLOC keep memory finite. One invocation runs one enumerated
scenario, writes its own fresh image using exclusive creation, then exits.
Parent-owned process groups and retained logs delimit each scope. No hardware,
mount, existing database, driver or hub service is opened or modified.

Upstream source is exact and its BSD license is retained. Assertions remain
enabled. Debug/warning/error printing is disabled only to keep stdout structured;
return codes and original probe checks remain active. Numerical callback counts
are observations, not a claimed benchmark across filesystems. A separate POSIX
comparison checks the behavior expected from our local file interface.

The source shows broader issues needing an adapter: file-handle coherence,
open-unlinked retention, inode identities and permissions, bounded recovery,
exact format/configuration, and reservations for transient COW allocation.
None of those is implemented or qualified by this probe.

The original runner verifies the archive and acquired file identities before
compilation, freezes the nine build/review/runner inputs, and uses the frozen
sources directly. It creates attempt01 once, records child intents, PIDs, output
and reaped status, and stops on the first failed or inconclusive scope. Compiler
and binary identities and the public 244-file baseline are checked again before
the successful observation receipt. Native POSIX comparison uses only a fresh
16-byte file. This is a local research harness, not a crash-qualified supervisor.
