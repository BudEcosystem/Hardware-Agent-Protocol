# Linux child subreaper contract

All three retained extracted manuals were read in full: 403 LF lines, including
their headings and preformatted blocks. HTML navigation and footer chrome are
outside the extraction. The acquisition manifest preserves its original
`unread` status; [reading.json](reading.json) records the later completed review.
No acquired code or process probe was executed for this research packet.

## Primary-source findings

[`PR_SET_CHILD_SUBREAPER`](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html)
sets or clears the calling process's subreaper attribute. An orphaned descendant
is reparented to its nearest living ancestor that is a subreaper. That ancestor
then receives the child's termination notification and can wait for its status.
The attribute is not inherited by children created through `fork` or `clone`,
but survives `execve` in the process that owns it. Setting a subreaper therefore
establishes an adoption point while that ancestor remains alive; it does not
make every descendant a subreaper. The operation takes a `long` setting and
returns zero on success or minus one with `errno` on failure.

[`PR_GET_CHILD_SUBREAPER`](https://man7.org/linux/man-pages/man2/PR_GET_CHILD_SUBREAPER.2const.html)
writes the caller's setting through an `int *`. The function's zero success
return is separate from the retrieved setting. An invalid output address can
produce `EFAULT`. A binding must inspect both the call result and the returned
integer, rather than treating a successful return as the enabled state.

[`prctl`](https://man7.org/linux/man-pages/man2/prctl.2.html) is a Linux interface
whose operation selects the meaning of its remaining arguments. Its libc
wrapper is variadic: numeric arguments must use the required width, including
`0L` for zero constants. Unsupported operations or nonzero unused arguments may
produce `EINVAL`. A small typed C binding can provide a checked integer API
while passing the pointer, `long` setting, and unused zeros with appropriate
types to libc. That binding remains specific to its declared platform.

## Retained local declarations

The complete 55-line `sys/prctl.h` snapshot was read. It declares the variadic
libc interface and includes Linux operation definitions. Only the subreaper
constants at lines 158–159 of the retained `linux/prctl.h` were reviewed:
SET is 36 and GET is 37. Retaining that complete header does not establish full
header review or qualification of all transitive build dependencies.

## Consequences for the HMS test harness

These are engineering conclusions from the documented contract, not additional
kernel guarantees. A dedicated live guardian can become the wait owner of
orphaned descendants and must collect their exit status. It should verify actual
child ownership before acquiring a live signaling handle. A stored process
number is insufficient evidence of that relationship.

Subreaper adoption alone supplies neither resource containment nor a physical
stop deadline. It does not promise successful cleanup after every guardian has
died. Separate process limits, ownership checks, bounded cleanup observations,
and actual controls are needed for any narrower implementation claim. This
packet documents the interface; implementation and execution evidence belong
to their own artifact packets.
