# Isolated mount-identity provider candidate

The preceding diagnostic found repeated mountinfo parsing expensive and reproduced
a stacked-mount selection error. This candidate uses a fresh held-descriptor and
pathname statx pair before every block operation. Admission joins the actual
legacy mount ID to one bounded mountinfo snapshot to establish exact ext4 type;
the boot-unique mount ID, device and inode are pinned for the owner's lifetime.
Unsupported or absent result-mask bits refuse admission; no statfs substitution.

Only the block provider's mount predicate and explicit profile change. All
ownership, allocation, inventory, range, fork, lock, poison and fsync paths stay
unchanged. The hierarchy is an exact copy with a subclass overriding the provider
source hash. Existing images, sealed stages and the public runtime are untouched.

Qualification order: build; native synthetic vectors; Python parser/admission
and actual unprivileged query controls; original 24 provider tests; original nine
hierarchy scopes (96 controls); paired original/candidate coarse workload (40
files, 20 directories, 426 steps); then the complete 4,270-file writer and cold
reader if earlier scopes pass. No unchanged retry after a failed scope. Retain
every output and partially written image. Failed images may only be independently
inspected through the existing strictly read-only native reconstruction.

Each ordinary child has 60 wall seconds, 40 CPU seconds, 512 MiB address space,
128 descriptors and 16 MiB per file. Builds have 30 wall / 20 CPU seconds. The
full writer and reader each retain the original 180 wall / 120 CPU seconds and
eight preallocated 16 MiB chunks. Total retained stage allocation must stay below
1 GiB. Do not relax geometry or deadlines to turn a failure into a pass.

No mount/namespace changes, administrator privileges, physical ports, flashing,
live inference or public installation. Synthetic syscall results do not establish
real mount-race coverage. Source references are upstream Linux v7.0 and glibc
2.39, not an audit of the running Ubuntu binaries. The private shared-library
loader remains the earlier hash-checked pathname prototype, not a newly
qualified public native loader. A passing storage workload alone does not qualify
SQLite integration, service quotas, physical power loss or device control.
