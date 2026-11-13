# Native exception API review

The retained [CPython v3.12.3 exception API](exceptions.rst) is now fully read:
1,222 LF lines, adding 1,184 previously unread lines. Across the original six
sources, coverage is 3,248/5,360 lines; only the initialization document remains
partial. The [receipt](reading.json) preserves exact source/range hashes and the
[previous record](previous-reading.json). This is a reading overlay on the
original acquisition, not a new upstream acquisition or newer-release review.
No acquired examples were executed; linked sources remain outside this coverage.

The API distinguishes propagating errors from already handled exceptions.
Cleanup must preserve or deliberately replace the former; normal C API success
does not generally clear it. Save/restore helpers have ownership rules, and the
older three-object interface is deprecated in this version. Printing an exception
can terminate the process for `SystemExit`; it is not a neutral reporting step.

Warning calls can fail. `PyErr_SetFromErrno` can invoke Python signal handling
for `EINTR`. `PyErr_CheckSignals` handles signals only in the main thread of the
main interpreter; a zero result elsewhere does not establish cancellation.
Signal scheduling itself does not set the error indicator. Wakeup descriptors
require a valid nonblocking descriptor and main-thread use.

These contracts reinforce explicit resource cleanup and the existing narrow
host profile. They do not prove a filesystem-call deadline or an independent
device stop path. Driver and hub lifecycle providers still need their own
completion and reconciliation contracts. No native binary or runtime behavior
was changed by this reading.
