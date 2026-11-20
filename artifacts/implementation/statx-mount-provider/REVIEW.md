# Pre-execution review

The source review is in `research/host-contract/mount-predicate-source`.
Linux statx obtains mount identity from the resolved path's actual mount object
for both pathname and descriptor queries. The unique counter is assigned at
mount allocation; legacy IDs can be recycled after the mount is freed. A held
directory descriptor keeps its mount reference while admission obtains the
legacy ID and mountinfo record. glibc's ENOSYS emulation returns BASIC_STATS only,
so required mount-mask validation rejects it.

The helper validates bounded arguments, requests TYPE, INO and precisely one
mount-ID mask, checks both returned masks, requires directories and nonzero
identities, and compares all four exported identity fields. Its error output is
zero. No DONT_SYNC request, heap, descriptor acquisition, mount mutation or
privilege escalation is present. Test-only syscall substitution compiles the
same helper body into a separate executable. Production has no substitution.

Admission is UNIQUE -> legacy -> bounded binary inventory -> UNIQUE. The record
is chosen by ID, with exact device, path-component prefix and ext4 checks. Binary
parsing splits only the actual ASCII field and line separators, preserving
carriage returns and non-UTF-8 pathname bytes. A source named '-' is valid.
Duplicate IDs and malformed records refuse. Current verification queries both
views again and compares mount ID, inode and device with the pin.

The provider patch contains only the new module import/profile, the admission
and verification wrappers, and replacement of the old repeated parser call.
Other provider behavior is byte-for-byte preserved. The separate subclass only
changes BLOCK_HASH. Hierarchy controls only change the Store binding; the coarse
comparison only changes the hierarchy module binding. The original provider
tests remain exact. These differences are recorded as patches and frozen inputs.

Limits: this is a trusted-host, exclusive-owner prototype. Two statx calls do
not make arbitrary concurrent namespace changes atomic. Mount identity does not
freeze every mutable mount flag or idmap; the original metadata checks still
run. No real overmount, unmount or mount-namespace change is performed. Missing
UNIQUE support rejects this profile. Hash-before-dlopen is the existing private
loader convention, not a claim of a race-free public loader. This review is by
the primary agent; helper-agent quota is unavailable in this session.
