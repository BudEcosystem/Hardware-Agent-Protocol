# Block-read profile: complete selected regressions

Stage 87, 2026-11-09. The exact native library from the preceding
[capacity evaluation](../../implementation/chunk-store-capacity/README.md) now
passes **all six original semantic scopes / 54 checks and all 22 interruption
cases / 24 selected owner terminations**. [Original results](attempt01/RESULTS.json).
The candidate, binary, oracles and operation boundaries are unchanged; sixteen
inputs are frozen. No capacity experiment or public runtime suite is repeated.

This host profile has 4,096-byte reads/cache, 16-byte programs and 4,096 blocks
per 16 MiB image. Every provider ownership/allocation check remains active.
The exact library SHA-256 is
`be8b43b7ad909ed65b9ee834fccee3a769f08091c6fc0d1ad48a8ad14bd9abc2`.
The larger native cache does not establish an Arduino memory profile.

The matrix covers create, namespace staging/publication, extension, within- and
between-chunk writes, shrink/grow, rename-over-target, unlink, final-reference
reclamation and two interruptions of recovery itself. The original pidfd-based
parents observe selected stops, terminate the matching owner and reap it. Recovery
uses exact copies with new host anchors. All original interrupted images remain
unchanged. The before-rename-sync cut observes the complete new namespace while
the host kernel/cache stays alive; physical power loss is not tested.

The [read-only audit](EVIDENCE-AUDIT.json) reconstructs the expected namespace and
payload from all **52 retained images**, verifies **208 distinct object anchors**,
joins original intents/checkpoints/copy lineage and confirms **75 recorded process
PIDs are absent**. It invokes no recovery and changes no image bytes. The first audit omitted the semantic recovery child from its expected total and
stopped at the count check. Its source and failure remain retained; the corrected
audit verifies the exact complete set of 75 process paths. The intentional
missing referenced chunk in the corruption-refusal scope stays missing.

Backing totals **832 MiB** within this separate stage's predeclared 1 GiB ceiling.
Original 60/40-second scope and 15/10-second selected interruption owner wall/CPU limits remain unchanged.
The [stage audit](AUDIT.json) verifies all 244 public runtime inputs against the
existing 866-test passing receipt and the prior sealed capacity artifact.
[Exact inventory](index.json). Review is by the primary agent only.

These results clear the selected regression gate for further private host
integration. Nothing is installed into the public runtime. The earlier small-cache
capacity failure remains a failure; the separate block-read exhaustion observations
remain intact. The actual SQLite DELETE/EXTRA interface, every-writer confinement,
backed continuation capacity and complete control-only service recovery still need
implementation and qualification. The flat 16-inode adapter cannot yet host the
complete service's hierarchy and writers. [Next work](NEXT.md).
