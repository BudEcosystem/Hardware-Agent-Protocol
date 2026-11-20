# Draft result review — independent audit pending

Root observed the original fixed run pass all13 owner-death cases. It reaped39
inner children:13 intentionally killed owners,13 successful recovery hosts and13
native peers exiting cleanly on EOF. The outer control also exited0 and was
reaped. Owners were empty/closed, with no cleanup errors, pending interrupts or
unexpected adopted children. The observed control interval was22.150156088 seconds;
final elapsed including cleanup/source verification was22.943975796 seconds.
The recorded control CPU use was16.270212 seconds, under the unchanged30-second
profile. RESULT SHA256:
`c7dc7de7f0bf5f8b70ab1037f7894c9e5b8518c289e0d24b3be1e33ae26a4f77`.

The13 cuts cover prepared/possible/reply boundaries for OPEN, START, ACK and RETIRE,
plus collection committed before ACK reservation. The original native peer stayed
alive across each owner death and fresh recovery. Parent-observed read-only
recovery precedes any separately requested new action; no uncertain original is
resent. Prepared originals retain their old identities when explicitly abandoned.
The retained outcomes include three released retired/abandoned deployments,
four possible-send deployments retaining all three claims, and six other accepted
or explicitly settled deployments retaining ownership.

All287 reviewed inputs remain unchanged. The source review SHA is
`4dca9bff924a726520952e9beae2a4b7d18bd73f46a4735e2fd1c227f2aba9fe`.
The harness consumed the existing native image and qualification bundle at the
original host-attempt04 absolute root; it did not compile or rerun the evaluator.
The existing20-case/173-check host pass and original12-case/638-assertion evaluator
remain prerequisite evidence rather than new results of this harness.

A standalone retained-data audit has been prepared but not executed. These draft
notes report the observed original run, not a completed independent audit or seal.
The actual process-death evidence qualifies only these fixed complete-transaction/
complete-frame cuts with the living guardian and synthetic peer. It does not
qualify arbitrary process death, partial frames, SQLite COMMIT interruption,
power loss, full storage pressure, physical I/O, protected capacity, GPU readiness
or the entire prompted-application system.
