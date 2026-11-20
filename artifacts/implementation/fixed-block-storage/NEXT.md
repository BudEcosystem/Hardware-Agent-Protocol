# Next: qualify the storage interface and complete the service

The fixed block layer is an isolated prerequisite. Keep the passing and failed
attempts and all preceding sealed evidence unchanged; use new owned paths for
new experiments. Do not repeat the unchanged 866-test public suite or thirty-case
worker for this documentation/prototype stage.

1. Acquire and fully read the pinned littlefs core, public and utility headers,
   design, on-disk specification and relevant test/dependency sources. Record
   suitability for the actual storage contract before building acquired code.
   The stock wrapper and fuse2fs are not accepted providers. A custom interface
   or a separately provisioned native filesystem remains an alternative if the
   reviewed semantics do not fit.
2. Design the complete filesystem/provider profile: finite blocks and inodes,
   metadata overhead, lock and sync semantics, exact file identity, rename,
   directory durability, retained open-unlinked ownership, daemon termination,
   mount ownership/propagation and bounded request queues. Assess the exact
   SQLite journal mode and VFS behavior; do not infer compatibility from normal
   file reads/writes. Never format a failed recovery mount.
3. Preserve explicit finite scratch/process limits. Test allocation exhaustion,
   metadata exhaustion, partial/error I/O, interruption, daemon loss and cold
   recovery on fresh retained fixtures. Distinguish injected syscall faults,
   process interruption and actual hardware power loss. The block layer's erase
   and zero-length paths, root/UID changes and broader filesystem error matrix
   have not each received dedicated controls in this 24-test stage.
4. Compose a trusted owner with separate control and bulk storage. Every writer
   and side file must stay inside aggregate enforcement, including temporary
   files, code images and open-unlinked objects. Set/read back connection caps
   before startup/recovery mutations. Admit work only after backing its finite
   remaining control continuations. Retain control-only recovery when bulk
   evidence is missing/full. A quota or free-space counter alone is insufficient.
5. Integrate installed qualification libraries with durable original attempt and
   input associations, complete candidate inventory, current dependency/binding
   checks, held evidence through commit and reproducible service configuration.
   Then expose typed public PAT tools without changing operation replay or
   cancellation semantics. Unavailable evidence must not be classified as novelty.

The product requirement spans device I/O, drivers and the intelligence host.
Learning proposes validated PATs for declared contexts; deterministic execution
uses installed capabilities without model inference for each ordinary action.
Driver updates and hub restarts change dependencies and require reconciliation
and revalidation. Commissioned endpoint control and physical stop behavior must
remain available during model/hub outages. Actual providers, persistent MCU
programs, prompt learning, microscope commissioning, native Harness integration
and home/laboratory/manufacturing qualification remain in the active goal.
