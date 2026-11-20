# Source review and diagnostic boundaries

The complete fixed-block provider (312 LF lines) and native Python transport
(123 LF lines) were read this turn. The hierarchy's complete create, metadata,
identity-reservation and publication methods were read again; the exact full
hierarchy and C bridge were reviewed in stage 91. The underlying sources and
binary are reused byte-for-byte, including the littlefs core previously read in
full. No new upstream code is acquired or executed.

`FixedBlockImage._perform` serializes and calls `_verify` before the positional
read/write or flush. `_verify` checks process/poison state, held and named root
ownership, mount identity, exact directory inventory, held/named file metadata,
and the complete owner/manifest bytes. `_host` opens and bounds `/proc/self/mountinfo`
then parses it on each invocation. `sync` fsyncs every backing chunk. Erase calls
the same validated write path. The C bridge has a 4 KiB read/cache and synchronous
file write/sync/close; no native per-file handle is exposed to the adapter.

The diagnostic loader calls the original checked module loader, then wraps that
module's original functions and subclasses its provider with wrappers around
unchanged inherited method bodies. An OS proxy forwards selected functions to
the original `os` module; it does not modify global `os`. Native transport wrapping
changes only `Native.call`, forwarding its original arguments and exceptions.
All data functions and the hierarchy source remain exact. Both modes retain
logical operation timing and write/read oracles. Only `nested` adds lower spans.

Spans use a single-threaded stack and monotonic/process clocks. Exclusive time
subtracts direct child spans. Wrapper bookkeeping outside each span is not removed
from caller time. Native exclusive time includes bridge/ctypes/callback glue and
untimed wrapper overhead; it is not a pure C execution measurement. Mount-check
exclusive time includes buffered proc-file I/O and parsing; it does not isolate
those costs. OS-call timings include Python wrappers and kernel work, not a
separate syscall trace. These limitations constrain any performance conclusion.

The diagnostic is a local host screen. Whole-service performance, large-body and
high-occupancy behavior, every hierarchical interruption and physical power loss
remain unqualified. Review is by the primary agent; helper-agent quota remains
unavailable. All successful and failed preceding results remain unchanged.
