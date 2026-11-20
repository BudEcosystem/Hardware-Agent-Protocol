# Bounded runner source review

Status: source-only correction for parent review. This runner, its borrowed helper, compilers, native probes and target image have **not** been executed during this correction. No project C/header/control file was edited by this lane. The standalone runner is not yet a passing execution receipt.

Reviewed candidate runner SHA256: `a3d6317bb0a4fe39eb884c9654dc558505b61b99ddda57b9f2ced4faaa2d7099`. Original copied runner SHA256: `5bcbc9bff30e11bb905f0fddb99b59a8f7eeb25ccd3e0e78a33f1275ce0a4cb3`. The original remains in `originals/run_checks.py` for an exact diff.

## Ownership and interruption changes

The runner uses an exact copy of the already reviewed dedicated `Guardian` from the sealed owned-hub-crash-harness packet. It loads the existing pinned owner/subreaper library from a sealed memfd when the approved runner is eventually invoked. Its platform contract is Linux/glibc/x86-64 with CPython3.12, optimization disabled, one native thread, raw SIGCHLD default without NOCLDWAIT, no competing reaper, no children initially, and exclusive ownership of the runner's subreaper attribute. These are explicit gates, not assumptions inferred from Python's `getsignal()` alone.

INT/TERM are masked across `Popen` return/assignment, retained Popen-object capture, Guardian registration and the per-command started receipt. The child resets those dispositions and restores the prior signal mask before exec. Any interrupt delivered on parent unmasking is caught by the enclosing cleanup path. Popen objects are retained until their exit codes have been assigned from the actual kernel reap, so their destructors cannot become a competing reaper.

Group signals require the still-unreaped, registered direct leader, verified kernel child relation, start identity and original session/group. The leader is reaped only after group cleanup. Adopted compiler descendants are registered through the dedicated subreaper's kernel child relation, signaled with retained pidfds and reaped. No group signal follows leader reap. Later numeric PGID scans are observations only and cannot authorize a signal.

Cleanup, reap bookkeeping, log flush/fsync and per-command result publication are masked. Pending INT/TERM refuses a passing command/stage result. An interrupt delivered after masked final stage publication is caught by the outer entrypoint, which records terminal failure before exiting. A source/clock/compiler failure retains the existing attempt instead of overwriting it with a later run.

The guardian must remain alive. Runner SIGKILL, host death, adversarial process escape and universal resource containment are not qualified by this adaptation. The reviewed guardian has a128-child registration bound. A failed ownership/observation/settlement check prevents a passing claim; the runner does not select arbitrary processes from saved PIDs.

## Input, executable and receipt changes

Each requested stage still requires a new `build/<stage>[-attempt-N]` and new `checks-<stage>[-attempt-N].json`. Existing paths refuse. Each command additionally has exclusive-created intent, started and result receipts plus exclusive-created stdout/stderr. Aggregate JSON is replaced atomically with fsync; per-command phases remain independently retained. Commands that never acquired a child cannot fabricate a started receipt.

Frozen execution inputs include the complete project source tree, runner, PLAN, WIRE, literal vectors, source pins, README, REVIEW, project source review/diff metadata, this runner review, borrowed-owner mapping and its four exact input copies. Generated receipts/build outputs are excluded from recursive source collection. Original and frozen source hashes are checked before/after every command and in the stage's final audit, including failure paths. This is a before/after byte observation of a trusted private build, not a filesystem-immutability claim.

The running interpreter ELF, selected interpreter path and held interpreter FD must agree. Native GCC is selected using the same fixed `/usr/bin:/bin` path exposed to the old suite. Its cc1/as/ld/collect2 selections are queried, pinned and checked before/after commands; the original nested suite's retained compiler identity must match that selection. Every direct `run()` argv executable is hashed through an opened read-only FD and executed through that FD, with the original argv0 retained. Private native outputs are likewise hashed before and after execution. Borrowed helper originals and frozen copies are checked. AVR archive-derived tools, headers, libraries and specs remain pinned before compilation and checked in the final audit.

The original suite launches its own reviewed fixed nested compiler/probe commands using the fixed environment; it does not use the outer runner's FD for those nested execs. Source/tool before/after checks and its own compiler receipt cover the observed selection. Native system headers, start objects/libraries, host standard library and dynamic loader remain trusted unpinned dependencies. This is not a complete native-toolchain or hostile-filesystem qualification.

The existing bounds remain30 CPU seconds per child,64MiB file limit,64 descriptors, zero core files,512MiB address space except ASan-required processes,60-second command wall monitoring and a512MiB PGID-RSS observation threshold sampled every20ms. Anchored group cleanup has a3-second observation window; pidfd/adopted-child settlement has an8-second bound. RSS samples are observations rather than a cgroup quota. No AVR ELF is executed, and no serial/device path is opened.

## Gates retained for eventual parent execution

The native stage retains the original finite suite and pipe smoke, original11-case/20000-step AVR register oracle, and exactly12 standing cases in plain and ASan/UBSan modes. AVR remains compile/link-only for the original ATmega328P/16MHz target. The256-byte primitive arena,128+32-byte standing accounting,64-byte protection reservation and unchanged physical memory caps remain checked. Stack/ISR analysis and physical/runtime fit remain separate unresolved evidence after linking.

The source review covered the complete modified runner, the copied Guardian ownership methods, raw precondition/subreaper C helpers, and the retained audit/crash-launcher interruption patterns. Data-only verification confirmed all four borrowed files exactly match their sealed originals and mapping hashes. It did not load the helper, import candidate modules, compile or run any check. Parent review of the stable runner is required before the first attempt.
