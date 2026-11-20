# Resource semantics: 31 tests pass

All [31 exact methods](../../harness01/targets.json) pass in 64.797 test seconds
and 73.084 elapsed seconds. See the [acquisition proof](proof.json),
[test log](attempt/output.log), [source review](../../implementation01/source-review.json)
and [design](../../DESIGN.md).

The pure composition verifies both sealed shared-board captures. It reconstructs
all four actor requests and descriptors, static timing, installed configuration,
trusted grants, observations, operation events, board transitions and returned
results. Each history has four admissions, three resource-busy refusals, four
dispatches, five exact replays, one historical read, 20 operation events, eight
receipt versions and 44 paired checkpoints. All four operations complete, with
no remaining authority claims or board owners. The GPIO probe is an original,
declared request and remains unadmitted because PWM holds its resource.

Tests reject altered reply identities and claims, false historical results,
coherently rehashed receipts with false effects or routes, hidden activations,
reset fences, forged owners, event/namespace/replay changes, wrong admission
revisions, changed grants/bindings, incorrect samples, hidden final operations,
probe-key substitution and skipped eligible dispatch. The reader's I/O/time
purity and explicit actor boundary also pass. These are primary-agent tests and
review, not an independent-agent review or physical measurements.

All 7,665 project inputs, 7,668 frozen entries, six active harness inputs and 159
external pins remain stable. Compiler/driver identities match; 733 actual-origin
records match and 230 cached-bytecode reads are refused. No SQLite connection,
network call, runtime execution or device action occurs. The complete 7,699-file
attempt and its empty original scratch directory are retained. Original 180-second,
16 MiB and 8,192-file bounds remain unchanged. The explicit closure excludes 947
clock-only fixtures, which remain intact in their original sealed stage.

Complete-history success applies only to this fixed provider/authority challenge.
The four literal actor domains are checked; a full candidate matrix, current
source/configuration attestation, actual aggregate quotas, public qualification,
prompt learning and physical/hub control remain incomplete. Their success flags
remain false. Existing single-actor regressions are recorded separately.
