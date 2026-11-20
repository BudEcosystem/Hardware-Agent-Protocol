# Native supervisor candidate

This fresh copy replaces the supervisor's Python metadata walker with the
previously verified original C binding. It changes neither the worker matrix nor
the requested storage, effect, deadline or evidence bounds. Logical-size scanning
is still not a filesystem quota or reserved capacity.

The strict wrapper accepts exact str/bytes/PosixPath/PurePosixPath inputs and plain
bounded integers. It rejects user conversion hooks. Native policy failures map to
the existing supervisor errors; OS errors preserve errno and identify the scan
root. Cleanup errno can be retained as an exception note. Native signal exceptions
propagate. The stronger root mode/owner and opened-child identity checks remain;
there is no fallback to the original weaker traversal. This is an explicit new
host profile, not full Python call-semantic equivalence.

The exact x86_64/CPython 3.12 DSO is included with its C source and Python wrapper
in `SOURCE_FILES`. The normal image and consumer identity machinery therefore
hashes and copies all three. Consumer identities are independently computed from
retained source and verified installed dependencies before the original test's
literal pin changes. The native DSO is unchanged from the binding controls.

At first valid use, a fixed bounded binary read checks exact SHA-256. Verified
bytes are written into a fresh executable Linux memfd, sealed against write,
growth, shrink and seal changes, and checked again before dynamic loading through
its held `/proc/self/fd` path. An on-disk replacement after verification cannot
select different executable bytes. The profile explicitly requests MFD_EXEC and
does not change kernel settings or retry through a filesystem bypass if local
policy rejects executable memfds. This Linux facility and readable procfs are
requirements of the selected profile; unsupported platforms refuse.

The loader owns at most one image descriptor for process lifetime. CLOEXEC avoids
inheritance through exec. Once dynamic loading can begin, the descriptor remains
held even if loading fails, preventing reuse of that loader-cache pathname. All
earlier failures release it. A failed loader remains unavailable for the process;
subsequent scans do not create replacement images. Loaded code has process memory
and authority; sealing is not a sandbox or protection from arbitrary same-process
code, debugger injection, interpreter mutation or privileged tampering.

Pre-load, sealed-image and pre-scan events give the execution harness explicit
authority boundaries. The harness must verify the acquired binary, image seals,
held inode and digest, authorize the exact supervisor/attempt paths, and record
the native module's origin separately from ordinary disk modules. Audit hooks do
not observe every native filesystem call and are cooperative controls. Native
scan syscall evidence comes from the preceding binding stage.

Six fresh owned-fixture processes test the wrapper, real kernel seals, second-fd
write refusal, reuse, error mapping, post-verification disk replacement, digest
failure, both audit veto points and bounded failure behavior. They execute no
worker, database, physical target, acquired upstream code or live service. The
full worker/import scope and retained audit remain required before adoption.
