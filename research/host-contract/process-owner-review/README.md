# Process ownership source review

Four primary Linux manual pages were acquired on 2026-11-09 and their complete
extracted manual content read: **1,250 LF lines**. The raw HTML, extraction
script, acquisition metadata and reading receipt are retained here. The pages
identify Linux man-pages 6.19; this is a dated source review, not a claim that
every installed kernel or language binding implements every documented flag.

| Primary manual | Extracted LF lines | Local text |
|---|---:|---|
| [pidfd_open(2)](https://man7.org/linux/man-pages/man2/pidfd_open.2.html) | 268 | [text](text/pidfd_open.2.txt) |
| [pidfd_send_signal(2)](https://man7.org/linux/man-pages/man2/pidfd_send_signal.2.html) | 249 | [text](text/pidfd_send_signal.2.txt) |
| [wait(2), including waitid](https://man7.org/linux/man-pages/man2/waitid.2.html) | 499 | [text](text/waitid.2.txt) |
| [setpgid/getpgrp(2)](https://man7.org/linux/man-pages/man2/getpgrp.2.html) | 234 | [text](text/getpgrp.2.txt) |

The extraction retains every h1/h2 heading and every preformatted manual block,
including examples, errors, notes, history, references and colophon. HTML
navigation and footer chrome are outside the reading claim. No manual example,
acquired program, compiler, process-control probe or candidate provider executes
in this packet. The acquisition script performs HTTPS reads and writes only its
new packet files.

The primary agent also fully re-read the current public
[QualificationSupervisor](../../../hms_qualification/supervisor/qualification_supervisor.py).
Its exact hash is in [reading.json](reading.json); this is a source comparison,
not a new qualification result. [Notes](NOTES.md) connect the documented
interfaces to the actual ownership, cancellation and recovery boundaries.
The owned hub-job implementation remains a separate candidate, and this review
does not authorize changing simulation-only public policy or claim a process
group is an arbitrary-code sandbox.
