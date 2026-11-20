# Next: actual service storage contract

Keep this stage and all earlier failures sealed. The exact block-read host profile
has passed its selected regressions and already has separate actual allocator
exhaustion observations. Do not repeat unchanged suites or interpret those gates
as a complete service or physical-durability qualification.

1. Inventory the actual control and bulk writers from the current public service
   sources: database/journal/temp files, worker inputs and outputs, code images,
   archives, locks, sidefiles, open-unlinked objects and surviving producer owners.
   Define required namespace/hierarchy, ownership, lifecycle, locking and sync
   behavior before building the interface. The current flat 16-inode profile is
   insufficient; raising that cap alone does not settle the complete contract.
2. Choose and freeze complete domain capacities and interface semantics. A custom
   FUSE filesystem could expose the allocator to all supported writers; a SQLite
   VFS by itself does not constrain non-SQLite writers. Existing stock wrappers
   are not accepted providers. Preserve the declared trusted-code threat model
   and explicitly account for writer bypass, mount replacement and daemon loss.
3. Implement the selected interface and verify actual SQLite DELETE/EXTRA hot-
   journal recovery, directory sync, locks and failure semantics. Connection caps
   must be read back before any startup/recovery mutation. No silent durability
   change, implicit domain growth or metadata reserve claim is permitted.
4. Back remaining control continuations with usable capacity including transient
   metadata and reclamation costs. Test complete control-only recovery with bulk
   full, missing and unavailable. Preserve unresolved effects and original keys.
5. Integrate public qualification ownership and typed PAT tools, then the full
   prompt-to-agent-to-qualified-PAT learning and deterministic reuse flow.

Unified device I/O, bus/driver lifecycle and intelligence-hub providers remain
required. Local physical stop and qualified endpoint outage behavior cannot depend
on the model or this storage daemon. Persistent MCU programs, microscope hardware,
native Harness installation, remaining research and home/laboratory/manufacturing
qualification remain part of the active goal.
