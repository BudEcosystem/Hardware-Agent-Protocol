# Hierarchical shared-inode chunk-store candidate

Stage 91, 2026-11-09. The preceding split-supervisor integration is verified
progress: 71 distinct controls and the complete original thirty-case simulated
qualification-to-PAT flow pass, with its failed diagnostic batch retained. Keep
that seal, all original images and the 244 public runtime inputs unchanged.

Implement a separate bounded namespace over the exact reviewed fixed-block and
littlefs core. Retain 4 KiB data chunks, shared inode state, synchronous native
operations, ownership checks on every provider I/O, poison-on-uncertain-error,
stable handles and open-unlinked retention. Replace the flat single-document
namespace with checked per-inode metadata and directory entries containing stable
inode references. Use bounded shards for internal inode directories. A staged
entry publishes only after its inode is durable. Native rename moves the entry;
logical directory subtrees stay attached to their stable identities. Validate the
complete graph and backing inventory before adapter recovery writes.

Profile: at most 8,192 logical inodes, 64 live handles, 32 logical directory levels,
255 UTF-8 bytes per component, 4,095 path bytes, 16 MiB per logical file and 64 KiB
per transfer. Links, arbitrary ownership changes and modes outside private 0600/
0700 are unsupported. The native entry ABI changes to 264 bytes and its name cap
to 255; cache/read size remains 4,096, program size 16, internal file cap 16 KiB,
inline files disabled and relocation disabled. This profile is distinct from the
previous binary. The fixed provider retains its existing maximum of eight 16 MiB
backing chunks, without implicit growth. This is a host profile, not an MCU claim.

Run meaningful independent semantic scopes on fresh one-chunk images with
60-second wall / 40-second CPU, 512 MiB address space, 128 FDs and 16 MiB per-file
bounds. Cover hierarchy, descriptor-relative access, rename/replacement, retained
open-unlinked files/directories, data coherence, sparse/truncate behavior, limits,
invalid request no-I/O, owner loss, corruption refusal and callback failure.
Record exact checkpoints and retained original state; never format failed mounts.

If those pass, replay the entire current 4,270-file / 35,508,922-byte workflow
snapshot, including every directory and full file body, into one fresh eight-chunk
128 MiB image. This exercises namespace fidelity, not domain isolation or a live
HMS service. The writer and separate cold full-content reader each have declared
180-second wall / 120-second CPU limits and the same memory, FD and per-file caps.
No smaller dataset, geometry growth or unchanged retry follows a failure.

Keep total new stage inventory plus original raw fixtures below 1 GiB. Freeze
sources, compiler, native binary, inputs and harness before use. Read-only audit
retained images/receipts and preserve all failures. OS mounts, SQLite VFS/FUSE,
byte-range/flock semantics across clients, physical power loss, hard every-writer
service quotas and backed control continuations remain separate qualification
work. The full prompt-to-PAT, device/driver/hub, MCU, microscope, Harness, research
and scenario goal remains active.
