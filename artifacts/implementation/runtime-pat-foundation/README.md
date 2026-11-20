# PAT foundation in the main runtime

**All 861 runtime tests pass**, including all 748 original test identities and
113 new foundation checks. The run takes 512.521 seconds, with all 161 inputs
and compiler identity unchanged. The [runtime receipt](runtime-receipt.json),
[results](RESULTS.json) and [independent source audit](integration-audit.json)
retain the outcome. This is a local simulation, transport and recovery result.

Eight production modules from the sealed
[vault/catalog candidate](../pat-vault-catalog/README.md) are now integrated into
the main `hms` package. Their bytes are unchanged. This advances the shared
runtime used for device I/O and the proposed driver/hub providers; public
qualification and PAT tool mounting remain separate work.

The integrated changes provide:

- Final trusted validation immediately before a Journal business commit, with
  rollback on failure and original-key reconciliation after a lost commit reply.
- Bounded compiler identity acquisition covering seven selected dependency
  packages, plus explicit fixed-schema unit metadata for typed I/O arguments.
- Exact-byte canonicalization for integer JSON, falling back to the original
  encoder for floats or changed dependencies.
- Bounded static topology and installation reuse, with fresh source checks,
  detached results and separate proofs for each instance.
- An explicitly selected 1,024-byte SQLite page layout for host simulations,
  retaining the default layout and refusing incompatible reopen requests.

The compact layout is not a disk quota or a capacity reservation. The commit
callbacks are installed trusted code, not caller-provided code or a Python
sandbox. Static validation reuse does not cache live authority or resource
availability. These distinctions remain part of the runtime contract.

The [plan](PLAN.md), [selected source manifest](selected-source.json) and
[source/test comparison](integration-review.json) identify the exact integration.
All 151 source inputs from the preceding passing 748-test runtime are preserved
under `baseline/`, with its original immutable receipt. Production source and
test fixtures from the candidate are separately preserved under `selected-source/`.

The first [focused run](focused01/result.json) executed 113 methods: 111 passed
and two new canonicalization fixtures failed because they expected negative zero
to be accepted. The existing contract intentionally refuses negative zero.
Only those test values and their negative-zero refusal assertion were corrected;
the eight production modules remain exact copies. The failed inputs and complete
log remain retained. The subsequent complete runtime attempt passes all 861 tests.

The public test adaptations use unique temporary directories, retain the 24
Journal-only checks, and leave five vault-dependent methods in their original
isolated suite. The standalone timing experiment is also retained there rather
than included as a repeated runtime benchmark. Two test methods omit report-file
writes while preserving their exact count and semantic assertions. Compact
storage checks use the same public synthetic installation directly. Nine new
canonicalization methods check byte compatibility, fallback and refusal behavior.

Source identities change with this integration. Previously installed synthetic
I/O configurations keep their original pins and will refuse changed source;
they are not silently repinned or migrated. New simulation installations use
the existing `scripts/build_io_example.py` generator. The compiler identity has
its explicit `/0.2` profile and digest domain; historical qualification does not
become current qualification by changing a label.

Next work is deliberate supervisor/vault/catalog packaging, backed control
capacity and aggregate storage enforcement, then the public authenticated PAT
service. The forty isolated I/O qualification modules remain in their sealed
candidate. Natural-language synthesis and learning, persistent Arduino programs,
physical I/O, actual driver lifecycle and intelligence-hub providers remain
requirements of the active overall goal. The adjacent Harness checkout and
physical hardware are unchanged by this integration.

The [broad evidence audit](evidence-audit05/report.json) passes 63,876 hash
assertions across 45,733 files. It retains four failed audit attempts: missing
historical temporary compiler paths, an initially unsupported archive hard link,
a separate historical objdump path and a worker review pointing at changed live
source. The final auditor checks historical source against its exact full748
snapshot and current source against the full861 receipt.

All 69 historical compiler references are verified as 29 distinct members of the
pinned archive. Their old installed paths are absent and explicitly reported as
archive-only checks. No compiler is extracted, installed or executed. Eight
[verifier controls](archive-controls.json) cover present/missing installations,
altered bytes, missing members and invalid links. The nonpublishing diagnostic
and all failed audit inputs remain retained.

The [native exception reading overlay](../../../research/host-contract/native-exception-review/README.md)
completes one more retained primary text, adding 1,184 read LF lines. Five of the
six API texts are now complete; initialization coverage and the wider research
remain partial. This reading changes no native binary or runtime behavior.
