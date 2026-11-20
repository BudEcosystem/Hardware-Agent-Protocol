# CPython SQLite cache and cursor binding review

Both pinned CPython v3.12.3 files were downloaded and read in full: **2,659 LF
lines of `connection.c` and 1,366 of `cursor.c`, 4,025 total**. Eight untruncated
local-source reads cover every line. Raw responses, acquisition metadata and the
[reading record](reading.json) are retained. Included headers, generated clinic
headers and linked sources are not covered. No acquired code was compiled or
executed, and the upstream tag is not an attestation of this host's binary.

The connection initializer defaults to 128 cached statements and builds a
per-connection LRU wrapper. Explicit close clears that cache and closes blobs;
close does not implicitly commit. Authorizer replacement forwards to SQLite,
replaces the Python callback context and checks the result; this wrapper does not
itself clear the LRU. Callback contexts own callable/module references. Python
exceptions in authorizer callbacks deny access. Trace callback exceptions do not
enforce policy, and progress callbacks do not establish hard deadlines. Several
operations release the GIL around SQLite calls, so Python-level ownership still
matters. The implementation also distinguishes transaction/autocommit modes and
can start a new transaction after commit or rollback. [Connection source](https://raw.githubusercontent.com/python/cpython/v3.12.3/Modules/_sqlite/connection.c)

Execution obtains a statement using the SQL operation as the cache key, resets
it, binds current parameters and steps it. A busy cached statement causes a
separate preparation. Cursor completion, close and cleanup reset/release the
statement; pending cursors can therefore keep extra statements alive beyond the
LRU entry count. Row conversion reads current SQLite values and can reject invalid
UTF-8. Implicit transaction setup and `executescript` prepare outside this normal
cached path; legacy `executescript` can commit a pending transaction first.
[Cursor source](https://raw.githubusercontent.com/python/cpython/v3.12.3/Modules/_sqlite/cursor.c)

HMS implications: evaluate the complete per-connection query set, preserve current
bindings and schema/type/size checks, and measure authorizer observations separately
from timing. Test previously prepared writes after installing each real HMS guard,
guard restoration, schema changes and pending cursors. A finite cache count is not
a complete native-memory bound. The experiment must keep a process memory cap and
explicit cursor/connection settlement; worker integration still needs the original
complete qualification and storage obligations.

This packet extends the [prepared-statement review](../sqlite-statement-cache/README.md).
It does not complete the broader research corpus or qualify a runtime cache change.
