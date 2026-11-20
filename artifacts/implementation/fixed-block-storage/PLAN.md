# Fixed-capacity block storage for the future filesystem provider

Stage 82, 2026-11-09. The preceding 14-check FUSE mechanism probe is verified
progress. Its files and all 244 public runtime inputs remain exact. The public
866-test baseline and complete thirty-case worker are not repeated unchanged.

Implement an original host block-image layer, separate from production. It owns
a finite array of regular files, each exactly 16 MiB, fully allocated and written
before publication. A closed manifest pins geometry and image identity. One to
eight chunks yield at most 128 MiB per image. The planned retained controls use
one two-chunk image and one one-chunk image: 48 MiB total, below the original
256 MiB scratch ceiling. No individual file may exceed 16 MiB. No physical device,
existing filesystem image, mount, package installation or privileged command is
modified. The read-only noninteractive sudo listing reported that a password is
required; no privileged command was executed.

Open existing images only, without creation/reformat fallback. Hold exclusive
ownership and exact file/directory descriptors. Creation returns device/inode
anchors for every object, which the service must retain in trusted configuration
outside the image. Reopen requires those exact anchors; a self-described manifest
cannot authorize replacement. Lock every backing object. Reject symlinks, foreign owners,
extra names, missing/replaced files, changed geometry and insufficient allocation.
Only aligned bounded block reads, writes, erases and explicit sync are exposed.
Use positional I/O, handle positive short transfers, and fail on zero progress.
I/O or image-integrity failure poisons that handle; close does not promise sync.
Known invalid call ranges are rejected before any data I/O.

This is a Linux/ext4 host profile under trusted code/kernel/owner and functioning
storage assumptions. Preallocation plus full initialization is real allocation,
but does not establish hardware power-loss behavior or a filesystem transaction.
Payload integrity, virtual inode limits, open-unlinked ownership, reserved
continuations and every-writer confinement still belong to the subsequent
filesystem/service layers. The layer cannot claim totalDiskQuotaEnforced or
backedControlCapacity for the HMS service.

Use actual retained files for boundary, reopen, ownership and mutation checks.
Label short-transfer/EIO/fsync injection as injected syscall behavior. Do not
fill the host filesystem. Verify fixed lengths/allocation and outside-boundary
sentinels, cross-process exclusion, missing/replaced state refusal, explicit
sync/reopen and failure poisoning. Keep partial writes when failure is injected;
never call them rolled back. Retain the ordered control log and original images.

The littlefs core remains a candidate requiring complete design/source reading
and qualification. Its stock FUSE wrapper is not a drop-in provider: it has
different API/metadata semantics and a minimal block wrapper. No acquired
filesystem/controller code is built or run in this stage. Native ext4 provisioning
would require administrator work, so the next unprivileged candidate uses this
fixed backing layer with a separately reviewed filesystem implementation.
