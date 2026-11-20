# Native supervisor worker accounting

Status: verified diagnostic progress; the complete qualification **still fails**.
All 291 project files and producer/consumer identities are unchanged from the
[native candidate](../../implementation/pat-native-supervisor/implementation02/README.md).
The public runtime and physical-device providers are unchanged.

The exact earlier process observer is composed with the native-aware harness.
All **21 pure controls pass**: fifteen observer controls and six composition
controls. The latter cover native vetoes, original launch refusal, duplicate
launches, separate scan/launch bookkeeping and terminal attribution to the
original process object. Their fake-process fixtures do not constitute another
real sealed-image test. Earlier loader/guard evidence remains separately retained.

The complete actual scope requests all thirty cases under the original 60-second
worker and 180-second parent limits. It retains thirty case directories and
twenty-nine manifests, then reaches `SUPERVISOR_DEADLINE` during `shared_resources`.
The original poll observes exit -15. No complete worker return, evidence import,
publication or source PAT application follows. Interrupted worker effects remain
unknown; twenty-nine manifests are not a qualified thirty-case result.

| Launch-to-reap observation | Value |
|---|---:|
| Elapsed interval bounds | 60.040232737–60.040989119 s |
| Supervisor CPU | 10.794492 s |
| Waited-worker CPU | 35.853978 s |
| Supervisor user / system CPU | 2.295473 / 8.499019 s |
| Worker user / system CPU | 33.433486 / 2.420492 s |
| Raw child peak RSS | 70,144 KiB |
| Verified native scan calls | 1 root + 2,400 attempt |

The four accounting snapshots take 306,388, 280,920, 475,462 and 655,992 ns.
Global CPU, memory and I/O pressure records are available. They do not attribute
waiting to this worker. Block-operation counters are not bytes or elapsed time;
peak RSS is not differenced. Neither these snapshots nor comparisons with earlier
trials remove observer overhead, identify a timeout cause or establish a matched
whole-worker speedup.

The read-only [audit](audit_actual.py) independently derives the observations and
associates the single original process object with its launch, ledger and inherited
directory/input/writer descriptors. Under **55 original owner/writer locks**, it
verifies all **3,960 retained files / 18,697,016 bytes**, 265 producer-image files,
the three consumer identities, and four unchanged source databases. It opens
zero interrupted case databases. The source authority has one reservation/handoff,
zero import intents/publications/operations/claims, an empty vault and zero source
board effects. Those source-state facts do not resolve interrupted worker effects.

The native image was checked while its descriptor was held in the child. The
post-run audit verifies the recorded association and artifact bytes without
reopening the exited child's numeric descriptor path. The raw tree is retained
at `/tmp/hms-native-worker-accounting-6ol6cedj`; its future availability is not
guaranteed by this receipt, and the verified acquired copy is preserved here.

[Results](RESULTS.json), [original receipt](harness01/attempts/attempt01-accounting/result.json),
[accounting](harness01/attempts/attempt01-accounting/worker-accounting.json),
[controls](controls.json), [design](DESIGN.md), [scope](harness01/SCOPE.md),
[source-path review](PATH-REVIEW.md), [next work](NEXT.md).

The [API reading overlay](../../../research/host-contract/native-binding-api-review/README.md)
finishes four previously partial texts, adding 1,708 covered lines. Two other API
documents and linked references remain partial/unread. Review is by the primary
agent, not an independent reviewer. No MCU, physical endpoint, model inference,
live service or acquired controller executes. Natural-language synthesis,
validated learning, persistent Arduino control and actual I/O/driver/hub providers
remain requirements of the active, incomplete HMS goal.
