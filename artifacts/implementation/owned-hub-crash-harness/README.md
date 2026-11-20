# Dedicated hub owner-death harness

The original Linux/glibc/x86-64 harness passes twelve actual provider-owner-death cases against exact copies of the [recovery increment](../owned-hub-recovery/RESULTS-REVIEW.md). It deliberately kills its own fixed owner at each reviewed checkpoint. The live guardian obtains authority over orphan jobs through the kernel child relationship and held pidfds, then individually reaps them. Stored job PIDs never supply signaling authority.

The [actual attempt](owner-crash-attempt01/RESULTS.json) passes in 1.960245488 observed wall seconds: twelve owners killed, twenty controlled children reaped, plus the outer control process reaped. No descendants remain for the outer guardian to adopt after normal control completion. Sources, interpreter and all 244 public baseline inputs remain exact. These bounds describe this finite local run.

| Checkpoint group | Cases | Required recovered result |
| --- | ---: | --- |
| admitted through before_release | 6 | not_started |
| release_intent, gate_released, writer_settled | 3 | unknown; no invented output/exit status |
| before_reap, reaped, terminal_committed | 3 | exact existing completed receipt |

Every case reopens the durable ledger, preserves the original request identity, and verifies that historical start does not launch again. Completed receipts are checked against an independent sum. A live writer lease may delay reconciliation; this run does not guarantee deliberate coverage of a retained-writer deferral. Commit ordering, rather than receipt of a process output alone, separates known completion from uncertainty.

Two preceding controls remain distinct. The [helper build/control](helper-attempt01/RESULTS.json) passes nine attribute checks without creating children. The [adoption control](guardian-attempt01/RESULTS.json) passes two fixed separate-session fork trees, reaping all five tree members and the outer control process. That control verifies rejection of non-child registration before adoption. Its initial registration records need not contain the later session change; fresh source assertions check those transitions.

The [plan](CRASH-PLAN.md), [provider pins](provider-pins.json) and [independent evidence review](CRASH-EVIDENCE-REVIEW.md) delimit the claim. The guardian must remain alive; this is neither universal process containment nor a physical stop deadline. The provider is an isolated fixed CPU artifact, not a public service, GPU job, hardware driver or GB10 qualification. [Next obligations](NEXT.md) remain open.
