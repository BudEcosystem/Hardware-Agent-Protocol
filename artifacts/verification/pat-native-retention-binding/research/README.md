# CPython binding contract: partial primary-source reading

Six official sources are retained in the [acquisition receipt](acquisition.json),
totalling 5,360 LF lines. Five API documents come from the CPython v3.12.3 tag;
PEP 475 comes from the recorded upstream URL with exact content hash. The
[reading receipt](reading.json) records the reviewed ranges and hashes. Remaining
ranges and linked references are unread. No acquired example or controller runs.

The selected [signal-handling contract](https://docs.python.org/3.12/c-api/exceptions.html#c.PyErr_CheckSignals)
limits Python signal dispatch to the main thread/main interpreter. A raising
handler leaves an exception for the extension to propagate. Our scanner must
clean up before returning that exception; a worker-thread scan does not become
independently cancellable through this API.

The [thread-state contract](https://docs.python.org/3.12/c-api/init.html#releasing-the-gil-from-extension-code)
requires Python API calls with the GIL held. Blocking filesystem calls can run
outside it, with state restored before signal checks. This motivates capturing
errno inside the released region. This stage does not qualify subinterpreters
or finalization behavior.

The [module definition](https://docs.python.org/3.12/c-api/module.html#c.PyModuleDef)
supports a zero-size state declaration for this stateless scanner. Its test
instrumentation has global counters and is confined to separate fresh processes.
The [audit API](https://docs.python.org/3.12/c-api/sys.html#c.PySys_Audit)
can deliver the three exact ABI arguments and a veto exception. This supports an
explicit boundary event; it does not recreate per-entry Python audit coverage.

The [integer conversion contract](https://docs.python.org/3.12/c-api/long.html#c.PyLong_AsUnsignedLongLong)
requires checking the error indicator and overflow. Exact-type checks additionally
exclude subclasses and conversion hooks. Numeric limits are then checked without
unsigned masking.

[PEP 475](https://peps.python.org/pep-0475/) informs the interrupt policy: check
signals before retrying eligible interrupted operations. It treats close as a
special case, ignoring EINTR rather than repeating a descriptor number. This
binding conservatively reports cleanup EINTR, an intentional difference from the
Python close policy. It does not assert identical behavior for scandir or every
libc wrapper. Their complete implementations have not been acquired/read here.

Installed ExtensionFileLoader source was read in full and is retained as
`../build01/installed-loader.py.txt`. Module creation delegates to the dynamic
loader, so verification needs to precede creation. The evaluation uses an
explicit artifact path; its before/after checks do not provide atomic protection
against concurrent artifact replacement. A future production loader needs its
own immutable-artifact and authority contract.
