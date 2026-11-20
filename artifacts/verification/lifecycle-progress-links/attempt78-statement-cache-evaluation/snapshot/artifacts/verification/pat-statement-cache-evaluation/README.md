# Complete-capture prepared-statement evaluation

**The local integration screen passes; production is unchanged.** With the
authority connection cache increased from 128 to 256 compiled statements and
the board cache kept at 128, all **62 differential checks** match. The unchanged
capture methods reproduce all **46 baseline page bodies and table references**
across 22 authority, 7 board and 15 configuration tables. [Audited results](RESULTS.json)

The separate diagnostic records the same 164 authority SQL executions per capture
at every cache size. On each of three warm captures, statements with authorizer
events fall from **164 to 37**; all remaining observed statements are table-info
pragmas. The zero-cache diagnostic also reports 164. Board observations fall from
28 on the first capture to 7 thereafter for all variants. These are observations
of preparation/repreparation activity, not direct cache-miss counters or proof of
the earlier complete worker's timeout cause.

| Fixed local timing, sixteen full captures per sample | 128 statements | 256 statements |
|---|---:|---:|
| Median process CPU | 190,006,653 ns | 116,923,755 ns |
| Ratio of median sample CPU times | 1.0000 | 0.6154 |

All nine fixed alternating pairs are faster, with **38.46% lower median CPU**.
Two warmups precede each variant's samples; no diagnostic authorizer runs in
the timing lane. The original page-encoding and canonical-blob caches are used
at both capacities. This full-workload comparison is distinct from the rejected
metadata-query experiment. It substitutes memory evidence writing and excludes
durable I/O, reservations, publication and complete worker/service behavior.

The checks include fresh context/output rows, newly invalid types/documents,
schema changes, row overflow, current parameter binding and pending cursors.
The exact Journal transaction/commit-check and catalog evidence-check methods
reject warmed writes, forbidden functions/pragmas and transaction controls,
including swallowed refusals. Permitted reads, exception restoration and
reentry/nested-evidence failures retain their expected outcomes. Memory fixture
objects replace constructor ownership/recovery; the fixture caller aborts its
write when evidence is unavailable. These checks do not qualify the complete
catalog selection or turn trusted callbacks into a sandbox.

The child finishes in **4.448 seconds**, opens 154 fresh memory-only connections,
has at most four live concurrently and closes all of them. Peak process RSS is
28,548 KiB under the original 512 MiB address-space cap. A statement-count setting
does not reserve native bytes or bound extra busy-cursor statements. No persistent
database, runtime package, qualification worker, inference or physical endpoint
is used. The audit opens no databases and verifies 91 current frozen inputs,
85 preceding failed inputs and 69 borrowed source/data inputs.

The first preparation failed because dedenting changed multiline docstring
literals; the corrected extraction preserves all nine method ASTs. The first
child then stopped at its first exact-output assertion before timing: its memory
writer used base record profile `/0.1`, while the retained conflict-capture data
uses `/0.2`. [Evaluation 02](evaluation02/SOURCE_REVIEW.json) pins that profile to
the original subclass and changes only the fixture binding. A correction script
also rejected a mistranscribed input hash before copying files. Every original
failure remains retained. There was **one timing run**, with unchanged methods,
cache choices, cases and limits. Copied preparation records describe their earlier
version; the correction and current source review define the executed fixture.

[Decision](DECISION.json): advance to a separately frozen worker-integration
candidate, with no production adoption or repeated benchmark. [Next work](NEXT.md)
preserves the full thirty-case qualification and original deadlines. The
[binding-source review](../../../research/host-contract/sqlite-cache-binding/README.md)
adds 4,025 fully read LF lines and records cursor/callback lifetime constraints.
The complete HMS objective remains active and incomplete.
