# Next: explicit supervisor storage bindings

1. Build a separate candidate with distinct control and bulk ownership/bindings.
   Update every `ledger.root`/`ledger.fd` consumer identified by the source census,
   including archive import and image accounting; preserve exact operation keys,
   request digests, handoff order and original producer ownership. Introduce an
   explicit new storage profile instead of silently migrating old ledgers.
2. Keep control startup/status independent of bulk. Test missing/replaced bulk,
   failed launch after durable admission, inherited writer leases and interrupted
   original owners. Missing bulk must leave unresolved records and forbid fresh
   relaunch. A path split alone is not quota enforcement or backed capacity.
3. Add pre-open provider checks and actual per-connection capacity gates before
   schema/recovery writes. Retain the authority/vault DELETE/EXTRA contract;
   explicitly review the supervisor's existing FULL behavior for the new profile.
4. Implement hierarchical storage and native SQLite integration for the full writer
   set in CONTRACT.md, including temporary locations, locks, directories, open-
   unlinked files and code images. Preserve 16 MiB per-file and 256 MiB scratch
   limits. Freeze physical partitions only after deriving the complete bound.
5. Back remaining control continuations and verify full/missing bulk recovery with
   actual pending control work. Then run the full qualification-to-PAT path and
   integrate public ownership/tools. Keep physical providers, local stopping,
   MCU execution, Harness integration and the larger research/scenario goal active.

No unchanged public suite, storage regression matrix or capacity experiment needs
repetition for this source-only assessment. A changed candidate requires the
relevant original semantic, identity, process and recovery controls.
