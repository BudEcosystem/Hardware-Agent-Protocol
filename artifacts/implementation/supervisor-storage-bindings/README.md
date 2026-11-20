# Explicit supervisor storage bindings — candidate, validation incomplete

Stage 89, 2026-11-09. This isolated candidate adds a version-3 supervisor ledger
binding distinct control and bulk directories. Five existing production files
change and one module is added. The 309-file project contains the original
qualification tests plus the current public test overlay; the 312-file source
index freezes the project, identity report, review and patch.

Control construction and historical lookup are designed to avoid opening bulk.
Fresh admission, code images, launch, archive reading and recovery that needs
producer files use the pinned bulk identity and owner object. Legacy ledgers
retain their original profile. Existing attempt keys, handoff ordering and writer
leases are preserved. New-profile startup refuses journal/WAL/SHM sidecars before
opening SQLite. This does not implement hot-journal recovery, hard quotas, backed
continuation capacity or a public service.

The read-only import inspection passes with the approved dependency roots and
records a 268-file producer image. It opens no databases and starts no worker.
Its first setup omitted those roots and failed with
`PAT_COMPILER_IDENTITY_UNAVAILABLE`; the failed source and report are retained.
An initial preparation check also named the wrong second identity-pinned test
file. Its source and failure record are retained; the actual two files are
`test_vault_catalog_process.py` and `test_vault_original_run.py`. Their identity
literals are the only changes to existing test bodies.

The selected validation contains **71 controls in 14 scopes**, including 15 new
binding controls. **Only the first test started, and it errored before opening
SQLite.** The control runner incorrectly placed scratch below group-writable
workspace ancestors. The unchanged pathname guard refused that placement with
`UNSAFE_STATE_ANCESTOR`. Zero controls passed; the other 70 were not run. No split
ledger was created, no diagnostic lease child or qualification worker launched,
and no complete matrix or PAT application ran in this stage. The failed scope,
its exact 309-file project and empty scratch file inventory remain retained.
There was no experimental retry, limit increase or shared-directory chmod.

The [audit](AUDIT.json) verifies retained sources, the failed result, the cause's
ancestor metadata and all 244 unchanged public runtime inputs. It is an evidence
audit, not successful runtime validation. The previous 866-test public receipt
remains the public baseline; it does not cover this candidate.

[Plan](PLAN.md) · [source changes](implementation01/final.patch) ·
[selection](control-selection.json) · [failed control result](CONTROL_RESULTS.json) ·
[next work](NEXT.md). Physical I/O, driver and hub providers, prompt learning,
persistent MCU PATs, complete storage qualification and the wider goal remain
unfinished. Primary-agent review only.
