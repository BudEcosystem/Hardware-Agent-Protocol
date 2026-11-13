# Native binding API reading follow-up

Four previously partial primary texts are now fully read: CPython v3.12.3's
integer, system and module C API documents, and the previously acquired PEP 475.
Their 1,947 LF lines add 1,708 newly covered lines. Across the original six-source
packet, coverage is now 2,064 of 5,360 lines; the exception and initialization
documents remain partial. This overlay preserves the earlier sealed record.

[Reading receipt](reading.json) records exact hashes and ranges. The files are
copied from the [original acquisition](../../../artifacts/verification/pat-native-retention-binding/research/acquisition.json),
not represented as a new upstream acquisition or a review of a newer Python
release. Linked implementations, PEPs and issue discussions are not covered.
No acquired example runs.

The [integer API](long.rst) distinguishes exact integers from subclasses and
requires an error-indicator check when the conversion result can also be an error
sentinel. Some conversion functions invoke `__index__`; masked unsigned conversion
wraps values. The scanner's exact-type checks and bounded non-masking conversion
remain appropriate. Neither an unsigned result nor a compact-integer fast path
would substitute for those checks.

The [system API](sys.rst) makes audit events a failure-propagating boundary and
requires `Py_ssize_t` arguments for `#` formats. Audit-hook installation can be
silently refused by an existing hook; successful installation cannot be assumed
without control of that environment. Python path conversion can invoke `__fspath__`,
which reinforces the current wrapper's restriction to exact supported path types.
The fork and locale sections do not establish portability or safe interpreter
reinitialization for this loader.

The audit documentation describes a nonzero failure return. The current binding
checks for a negative return. Python-hook veto controls pass, but those controls
do not establish every possible C-hook/interpreter return convention. Treat this
as a review question before broadening the supported interpreter profile, not as
an established bypass or justification to alter the frozen binary. The relevant
interpreter implementation has not been read in this packet.

The [module API](module.rst) distinguishes single-phase singleton behavior from
multiple independently initialized module objects. Nonnegative `m_size` describes
module state, while subinterpreter/GIL support has additional requirements. A
zero-sized stateless scanner does not qualify the Python wrapper's global lock,
held executable descriptor or loader state for subinterpreters. Reference-stealing
behavior also differs between object-add helpers; initialization cleanup must
match the exact helper used. The current profile remains a single main-interpreter
host scope with a process-lifetime loaded image.

[PEP 475](pep-0475.rst) separates retries of interrupted operations from propagated
signal-handler exceptions, requires recomputing timeout budgets, and excludes
close/dup2 from ordinary retry behavior. Python handlers run in the main thread;
an event-loop wakeup descriptor is a separate mechanism. This does not grant a
blocking filesystem call a hard cancellation bound. Its historical Windows and
issue-status sections are not current platform qualification. The native binding
still reports a cleanup interruption instead of copying Python close's ignore
policy, and does not retry a possibly reused descriptor number.

The [native process-accounting diagnostic](../../../artifacts/verification/pat-native-worker-accounting/README.md)
keeps the exact scanner and project unchanged. This reading follow-up changes
neither its failed qualification result nor the scope of its platform claims.
