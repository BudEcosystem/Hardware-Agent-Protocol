# Host identity and persistence evidence

The full retained text of [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.txt), its [current errata](https://www.rfc-editor.org/errata/rfc8785), SQLite's [transaction page](https://www.sqlite.org/lang_transaction.html) and [WAL page](https://www.sqlite.org/wal.html) was read. Selected [pragma documentation](https://www.sqlite.org/pragma.html) covers synchronous mode, journal mode and foreign keys; the remainder is acquired but unread. SQLite syntax-diagram text labels were extracted; separate inspection of SVG path geometry remains open.

[manifest.jsonl](manifest.jsonl) pins downloads; [reading-host-full.json](reading-host-full.json) records complete/selected LF coverage separately. The WAL text has a final unterminated line: coverage includes it. Integrity auditing caught the initial newline-count omission and the receipt was corrected to the displayed full range. [repos.json](repos.json) pins `rfc8785.py` v0.1.4 at `4d9b161f6054301d98d0566e813d020fb019ee10`; both Python implementation modules, README and license were read completely. Other checkout files remain unread.

## Decisions and limitations

The [authorizer follow-up](authorizer-followup/NOTES.md) adds two fully read
official API bodies, including all 33 action-code rows. Downloads, exact text
coverage and an offline integrity check are retained separately. It informs the
trusted PAT verifier's SQL guard; the installed-host tests, rather than those
C API pages, establish cached-statement behavior for this Python/SQLite build.

RFC 8785 uses ECMAScript primitive serialization and recursive UTF-16 property ordering. Python's ordinary `sort_keys=True` is not a substitute. Preserve strings without normalization, reject duplicate decoded keys before a map overwrites them, and define numerical representation explicitly. Verified erratum 7920 recommends rejecting negative zero because canonicalization otherwise collapses it to zero; erratum 6292 corrects an ECMAScript section reference. The [host profile](../../spec/08-host-contract.md) adopts JCS with stricter input bounds and explicit numerical refusals.

The library's modules are unmodified and licensed under Apache-2.0, including their attribution to Andrew Rundgren's reference implementation. The [vendored dependency](../../hms/_vendor/README.md) is executed by the host tests after review. Independent comparison against Node checked 78,832 accepted binary64 samples and four complete intent digests without a mismatch; [review artifact](../../artifacts/verification/host-contract-review.json). This does not constitute exhaustive canonicalizer verification or a cryptographic audit. The tests also retain all Appendix B finite serialization examples and non-finite refusals.

Review artifacts preserve their input hashes. The parser review's `spec/02-execution.md` hash predates the subsequent link to the new host profile and explicit endpoint/control fields in its digest paragraph; all reviewed parser/schema/dependency code hashes still match. The journal review and current test artifact match their implementation/test sources.

SQLite supports one writer and explicit transaction rollback; failed statements do not universally roll back the whole transaction, so the wrapper explicitly handles rollback. Its current WAL page documents a race fixed in 3.51.3 and named backports; installed Python uses 3.45.1. This prototype selects rollback `DELETE` plus `EXTRA`, whose documented directory synchronization strengthens commit durability. Mode pragmas are checked, not assumed. Single-process ownership, per-transaction short locks and atomic intent/resource/replay records address local journal consistency; none makes the database transaction atomic with an external device effect.

The journal's clock floor is durable even when an expiry or late-evidence request is refused. Detected clock rollback blocks new authority; cancellation and evidence can still be recorded with explicit clamped timestamp quality. A failed clock-floor persistence poisons further mutations in the process. A storage/authority restore and trustworthy clock initialization remain deployment obligations. Process-kill tests, including interrupted transactions with real hot rollback journals, do not establish power-loss or storage-device behavior.

The ordinary mutation journal does not implement the separate bounded stop path required by the execution specification. A production stop must not depend on acquiring its writer lock or successfully committing a normal operation. Authentication, commissioned admission, controller-side fences/watchdogs and real effect verification remain outside this prototype.
