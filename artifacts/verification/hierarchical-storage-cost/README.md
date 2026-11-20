# Hierarchical storage: measured cost and a mount-parser counterexample

Stage 92, 2026-11-09. The previous hierarchy remains a partial result: 96 semantic
checks pass, but the complete 4,270-file replay times out. This new diagnostic
uses the **exact source and native binary**, with every ownership check and fsync
enabled. It does not repeat the failed workload or install a runtime change.

Both declared modes pass on fresh eight-chunk 128 MiB images. Each creates twenty
directories and forty deterministic files totaling **623,624 bytes**, then reads
every byte through warm and cold owners. All **426 logical operations**, per-step
callback deltas, full bodies and final image bytes match between coarse timing
and the nested trace. The [independent audit](EVIDENCE-AUDIT.json) reconstructs
both images using read-only descriptors and 22 original object anchors. It invokes
no recovery and changes no backing byte. [Measured attribution](ANALYSIS.json).

| Nested trace observation | Count | Inclusive time |
|---|---:|---:|
| Mount identity/parser checks | 23,780 | 7.380 CPU seconds; 8.006 wall seconds |
| Provider verification | 23,777 | 11.558 CPU seconds; includes mount checks |
| Host fsync calls | 13,724 | 1.243 CPU seconds; 6.352 wall seconds |
| Native block reads | 19,816 | 81,166,336 bytes read |

The mount check occupies **51.43% of the nested process's 14.349 CPU seconds**.
This is an intrusive attribution screen: the coarse process uses 10.494 CPU
seconds and 16.378 wall seconds; the nested process uses 14.349 and 20.390.
Wrapper overhead is partly charged to callers. Inclusive values overlap and
must not be added; the audit verifies the exclusive partitions. These two local
runs do not establish a speedup, the precise cause of the earlier full-workload
timeout, performance at late namespace occupancy, or the complete workload's fit.

The [complete manual-source packet](../../../research/host-contract/mount-identity/README.md)
adds **1,703 fully read LF lines** and confirms a synthetic correctness problem in
the old parser. At one mount point, stacked IDs `9` then `100` leave its returned
pin at `9`, because string ordering is not mount-stack resolution. No actual mount
or namespace is changed. Fresh named/held mount identity queries are the next
candidate mechanism; filesystem magic alone cannot establish exact ext4 type.
No replacement predicate is implemented or qualified by this stage.

The original failed replay, all prior seals and **244 public runtime inputs**
remain exact. The unchanged 866-test public suite is not repeated. Two backing
images total 256 MiB, within the new stage's separate 1 GiB bound. Every child
finishes within its declared 60-wall/40-CPU limits. Primary-agent review.

[Next work](NEXT.md) addresses the measured mount-check cost and confirmed parser
case without removing validation or changing durability. Full storage/SQLite
service behavior, every-writer quota enforcement, backed continuations, physical
providers, prompt/PAT learning, MCU control, microscope commissioning, Harness
installation, remaining research and domain qualification are still unfinished.
The original goal stays active.
