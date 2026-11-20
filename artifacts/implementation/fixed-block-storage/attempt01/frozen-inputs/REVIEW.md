# Pre-execution review

Primary-agent review; helpers are unavailable and no independent review is claimed.
No implementation or test has run before this review. The reviewed plan retains
48 MiB of fully initialized backing; the injected create failure occurs before
its first allocation and retains only an empty chunk plus owner metadata.

The implementation uses explicit fresh creation, then an existing-only open.
Its fixed manifest bytes reject extra or changed fields, duplicate keys and
alternate encodings without a permissive JSON parser. Caller-supplied expected
object anchors are a trusted installation input, not an authentication API.
Creation returns these anchors for durable service configuration outside the
image. Missing completion evidence after creation failure cannot be treated as
an accepted service installation; that association remains service work.

Review corrected several issues before freezing/execution: file type is checked
before opening so a FIFO cannot block and a device node is not intentionally
opened; every backing object is locked; reopening requires original device/inode
anchors rather than accepting replacement owner bytes; process identity is
checked before an inherited mutex; all exceptions during actual I/O poison the
handle, including an interrupted write. The tests include actual process and
fork checks plus explicitly labeled syscall injection.

The tests retain their files and stop on the first unexpected failure. Planned
metadata/sparse mutations are restored only after the expected refusal passes;
they concern known experimental bytes, never interrupted qualification databases.
The partial-write test first inspects the changed bytes and then explicitly syncs
that same known fixture. It does not classify the failed write as rolled back.
Close releases descriptors without an implicit durability claim.

The profile assumes a trusted kernel, owner and cooperative original code. It
does not confine hostile same-user writers, authenticate raw block contents,
prove atomic block writes, or implement filesystem transactions or inode
accounting. The host filesystem is checked as ext4 through the observed device
and mount table. Fully written allocation and exact descriptors do not prove
hardware power-loss behavior. Those limits remain explicit in all results.

The acquired littlefs wrapper is not executed. Its chmod/timestamp behavior,
permissions, directory iteration, allocation failure handling and FUSE API do
not satisfy the current host contract as-is. The littlefs core/design/spec must
be fully reviewed before integration. The acquired fuse2fs source remains a
separate pending full read; its observed no-write-journal warning is sufficient
to withhold adoption, not to claim a completed source audit.
