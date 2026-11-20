# Retained-state audit

After the single attempt terminates, audit its receipts and all retained images
without invoking `HierarchicalStore`, formatting, adapter recovery, SQLite or any
writer. Use the frozen native bridge with new read-only descriptors; every write,
erase and sync callback refuses. Hold original object locks, verify host anchors,
and compare all image bytes before/after inspection. The owner-replacement fixture
is inspected explicitly through its retained original owner object and must keep
the substituted owner visible. It is never repaired.

Reconstruct logical bodies from committed inode metadata and chunk bitmaps using
an independent reader. Check successful scope bodies, original/recovered creation
visibility, orphan retention/reclamation, both deliberate corruptions and raw
callback-failure state. The full replay must have exact original source membership.
If it fails, verify every completely recorded file and inspect the next possible
partial publication separately. A partial prefix does not qualify the workload;
do not run the dependent cold-reader experiment after writer failure.

One audit process has 90 seconds wall, 60 seconds CPU, 512 MiB address space,
128 descriptors and 16 MiB per-file limits. Its source is copied and hashed before
execution. A failed audit remains retained and does not authorize repeating the
storage experiment. Recheck frozen sources, all 244 public inputs, process
termination and the 1 GiB stage allocation bound before sealing the result.
