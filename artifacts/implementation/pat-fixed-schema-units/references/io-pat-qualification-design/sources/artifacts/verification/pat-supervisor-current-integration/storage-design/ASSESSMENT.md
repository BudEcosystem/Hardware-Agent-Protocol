This is a read-only feasibility assessment. The implemented supervisor still
reports `totalDiskQuotaEnforced=false`; no storage-enforcement provider has been
installed or tested. `host-readonly.json` records only that this workspace is on
`/`, ext4, with `rw,noatime`. That observation establishes neither quota support
nor quota enforcement. No mount, quota, filesystem feature, service UID, network
configuration or privilege was changed.

The smallest plausible next step is an administrator-preprovisioned storage
domain with hard block and inode limits, followed by a trusted provider that
checks its actual identity and enforcement before service admission. This is an
engineering recommendation, not a finding that this host already supplies it.

Candidate mechanisms and their limits:

- A dedicated project-quota tree is a concrete option. XFS distinguishes quota
  accounting from enforcement; hard block/inode limits refuse further allocation.
  Its managed trees assign project IDs and inheritance, constrain hard links,
  and exempt ID zero from enforcement. The provider must verify these properties,
  rather than accept a configured path or a usage report as evidence of a cap.
  [XFS quota manual](https://man7.org/linux/man-pages/man8/xfs_quota.8.html)
- Ext4 is another candidate only after explicit provisioning and verification.
  The retained local primary manual, `sources/ext4.5.roff`, documents the
  `project` feature and `prjquota` mount option; it says quota utilities must
  actually enable/manage quotas. The kernel separately describes project-quota
  metadata in the ext4 superblock. No such feature/enforcement probe was run on
  this host. [Ext4 superblock documentation](https://docs.kernel.org/filesystems/ext4/super.html)
- A dedicated, externally provisioned bounded filesystem is an alternative
  design. It needs fixed identity, bounded capacity and inode accounting, and
  assurance that every service writer stays within its storage scope. A sparse
  or thin backing store is not proof of reserved physical capacity. Provisioning
  and destructive capacity tests are outside this task.
- A dedicated service UID quota could bound that UID's files if its identity and
  writable paths are controlled. Applying a quota to the shared workspace user
  would be inappropriate. The Linux quota API supports user/group/project
  limits; descriptor-based `quotactl_fd` can identify the mounted filesystem
  without resolving a block-device path. Unsupported, disabled or inaccessible
  quota state must refuse admission. [Linux quota API](https://man7.org/linux/man-pages/man2/quotactl.2.html)
- A tmpfs size and inode cap can bound volatile scratch. Unmount loses its
  contents, so it cannot alone retain durable interrupted evidence; durable
  archival needs its own bounded domain.
  [Kernel tmpfs documentation](https://docs.kernel.org/filesystems/tmpfs.html)

The existing per-file `RLIMIT_FSIZE` does not add together all files. The cgroup
`io.max` interface controls bytes/operations per second, not cumulative retained
storage. Logical directory scans, free-space observations and SQLite-only page
limits likewise do not establish a bound covering this supervisor's multiple
files, code images and non-SQLite outputs. They can complement a real storage
provider, but cannot justify changing the current false quota claim.
[Resource-limit manual](https://man7.org/linux/man-pages/man2/getrlimit.2.html),
[kernel cgroup I/O documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html)

Proposed provider contract, not implemented:

1. Trusted configuration fixes one root, service identity and backend. Callers
   cannot select another directory or executable to bypass global single-flight
   or admission. An inspection returns a bounded closed record of filesystem
   identity, quota identity, units, hard blocks/inodes, enforcement status,
   scope and provider/configuration generation. Absence, unknown capability,
   accounting-only state, exempt identities or changed scope fail closed.
2. The scope includes inputs, code images, stdout/stderr, worker returns,
   SQLite database/journal/WAL/temp files, raw evidence, retained capsules and
   archives. The provider must cover all writers, including an inherited producer
   surviving owner loss. Per-attempt project IDs must not be assumed to compose
   into a hierarchical global quota; a global domain or explicit sum of isolated
   enforced domains is required.
3. Durable logical admission remains under the ledger's owner/transaction policy.
   It records the inspected provider identity and requested logical charge, then
   rechecks the scope before spawn. A maximum allocation cap does not reserve
   underlying free space or guarantee completion; ENOSPC, EDQUOT and I/O failures
   remain possible. The service must not describe a logical charge as allocated
   filesystem capacity unless a real provider guarantees that separately.
4. Protect control-record capacity from worker bulk exhaustion. A separately
   capped control domain plus capped bulk domain is one design; the total bound
   is their explicit sum. Without this separation or equivalent reserved control
   capability, worker quota exhaustion may prevent terminal archive writes.
   The already durable nonterminal record then remains unresolved. No cleanup
   may delete unresolved evidence or infer zero effects to reclaim a slot.
5. The threat contract remains trusted original code, trusted kernel and trusted
   quota administrator. Private paths and the Python socket veto are not an OS
   sandbox. A later hostile-code service would require a separate confinement
   design. Administrative quota changes or mount replacement need an explicit
   trusted policy and must invalidate new admissions when detected.

Planned negative acceptance checks; none were executed here:

- Many small files collectively exceed the hard byte limit while each is below
  RLIMIT_FSIZE; inode exhaustion is also refused.
- SQLite side files, temporary files, code-image creation and open-unlinked
  allocations are charged to the declared scope.
- Wrong project ID, missing inheritance, cross-project hardlink/rename attempts,
  exempt identities, accounting without enforcement, unsupported/read-denied
  quota status, and changed mounts fail closed.
- Scope/limit changes between inspection and spawn refuse new launch; owner loss
  retains both active producer ownership and its logical admission charge.
- Quota exhaustion leaves the prelaunch durable record and existing evidence
  intact, reports actual failure/unknown state, and never triggers a new key or
  automatic same-run rerun.

The read-only documentation acquisitions and hashes are in `acquisition.json`.
All six successful HTML acquisitions have retained text renderings; the local
ext4 manual is retained in compressed original and roff form. The earlier web
navigation to the kernel's dangling ext4/quota link returned HTTP 404 and was not
used as authority. No acquired executable/controller was run.
