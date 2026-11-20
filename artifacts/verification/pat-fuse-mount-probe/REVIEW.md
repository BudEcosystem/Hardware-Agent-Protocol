# Preparation review

Primary-agent review before execution. No independent reviewer is claimed.

The server uses the complete unmodified public struct definitions, API version
31, and an explicit read-only callback set. It accepts one absolute mount path;
the owning harness supplies only its fresh private path. It passes fixed mount
options internally and cannot accept arbitrary FUSE modules, options or data.
Offsets are checked before conversion and subtraction, reads are bounded by a
fixed document, and readdir provides next-entry offsets and honors a full buffer.
The filesystem does no callback I/O, supports no mutations and contains no device
nodes or symlinks. No acquired example code is compiled or executed.

The mount is observed through procfs before a separate bounded client accesses
it. The observer does not traverse a possibly stalled mount during startup.
The installed library is pinned before compilation and checked in the live
process mapping. Ordinary unmount requires the same retained mount entry.
Cleanup signals only owned child objects. Mount identity and cleanup errors
remain explicit in the result. No success is reported with a remaining mount.

The empty original configuration header does not synthesize ABI structures or
modify acquired headers. No selected call depends on LIBFUSE_BUILT_WITH_VERSIONED_SYMBOLS.
The matching release is an API selection, not proof that an upstream source tag
exactly reproduces the distribution's installed shared library.

The parent has finite waits and the server has an independent alarm and
parent-death signal. This does not qualify cleanup after arbitrary parent death,
kernel failure, host power loss, a stalled physical drive or hostile same-user
interference. No service or physical stop guarantee is inferred from a probe.
The public runtime's 244 input hashes are checked before and after; its unchanged
866-test receipt is retained, without a redundant full regression run.
