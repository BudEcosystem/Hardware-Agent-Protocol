# Whole-worker accounting research

Five retained primary documents have been read in full: **1,315 LF lines**.
[Acquisition](acquisition.json) preserves the original download-time `unread`
status; [reading](reading.json) records the later complete coverage and hashes.
The manual-page headings and non-`pre` text were also read. Their two image types
are a book cover and an analytics pixel; neither is technical figure evidence.
No downloaded example, linked reference or controller code was executed.

[Notes](NOTES.md) distinguish CPU accounting, pressure, scheduling counters and
process identity. This research supports a bounded diagnostic of the existing
failed qualification worker. It does not establish its timeout's cause, qualify a
PAT, or justify changing execution or storage limits.

The first diagnostic will bracket the one original worker with parent and waited
child accounting, retaining global pressure separately. It will use the actual
owned `Popen` object and the original attempt's inherited descriptors for
association. It will not sample a process by a reconstructed PID, infer waiting
causes from elapsed-minus-CPU time, or change scheduling settings. Per-thread
scheduler and cgroup attribution require additional source review.
