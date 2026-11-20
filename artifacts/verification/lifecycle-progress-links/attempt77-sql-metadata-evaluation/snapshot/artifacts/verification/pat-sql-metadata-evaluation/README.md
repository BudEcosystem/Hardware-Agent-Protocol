# Fresh SQL metadata comparison

**All 410 differential cases pass; the optimization is not adopted.** The
candidate combines configuration storage-class and cell-size aggregates after
the unchanged row-count guard. It saves one SQL call per accepted table but
fails the [declared performance screen](PLAN.md): median CPU is **6.33% higher**,
and only three of nine fixed pairs are faster. No repeated benchmark or new
qualification worker follows from this result. [Decision](DECISION.json)

The [audit](RESULTS.json) verifies 39 frozen inputs, 26 borrowed sources/data
files, before/after equality and the original bounded child's terminal success.
The 410 cases comprise 130 acceptances and 280 identical refusals. They cover
all fifteen configuration tables, all storage classes, row/page/byte boundaries,
schema drift, private metadata exclusion, malformed text and JSON, mixed-invalid
refusal order, selected changes around metadata/row acquisition and fresh reads
between captures. The fifteen retained baseline tables reproduce exact original
page bytes. Interrupted worker databases were never opened.

The [source review](SOURCE_REVIEW.json) verifies that schema/key/count checks and
the size/row/cell/page suffix remain AST-exact. All other module AST remains
unchanged, as do the legacy table method and seven public parser/encoder
definitions. Combined aggregation performs more work before refusing invalid
types; the separate row guard still rejects oversized tables first.

| Fixed local comparison | Original | Candidate |
|---|---:|---:|
| Median CPU per 240 table captures | 94,949,568 ns | 100,963,198 ns |
| SQL calls per accepted ordinary table | 5 | 4 |
| SQL calls per accepted public-metadata table | 6 | 5 |

Nine pairs alternate order, with sixteen captures per table per sample after
the fixed warmup. The child completed in 3.113 seconds under its original
30 CPU / 60 wall second bounds. It opened 852 fresh memory-only connections,
zero persistent databases and no HMS runtime package or qualification worker.
The declared memory evidence sink canonicalizes pages and returns digest
references; it substitutes durability, reservation and publication. Timings
therefore exclude fsync and do not qualify the whole worker. Selected mutation
boundaries do not establish arbitrary concurrent-writer equivalence.

The [statement-cache research](../../../research/host-contract/sqlite-statement-cache/README.md)
identifies a distinct hypothesis to measure next: the unchanged authority capture
has 164 distinct SQL statements, while the installed connection API reports a
default cache of 128 compiled statements. That static count does not prove
eviction or explain the failed qualification. [Next work](NEXT.md)

No production runtime change, physical I/O, driver/hub provider, inference,
promotion or application is delivered by this experiment. The complete HMS goal
remains active and incomplete.
