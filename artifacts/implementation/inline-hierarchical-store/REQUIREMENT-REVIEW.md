# Device, driver and intelligence-hub requirement review

A separate agent reviewed the existing I/O/hub and prompt-to-PAT specifications.
The resource categories and lifecycle actions were already explicit. Its three
concrete documentation findings were corrected, then read by the primary agent:

- Deterministic reuse avoids planning inference. A pinned perception model can
  remain a declared PAT dependency with its own compute and evidence budget.
- Both routing diagrams now show unavailable evidence refusing admission, and
  unresolved outcomes reconciling the original operation before a new attempt.
- Richer control flow is labeled as a proposed future context-program profile.
  The implemented hms.pat/0.1 bound-sequence profile still rejects branches,
  loops, dynamic observations and sustained guards.

The review changed prose only in docs/io-driver-hub-control.md and
docs/prompt-to-pat.md. It did not alter public schemas or runtime code or claim
implemented persistent triggers, concrete hub capacity/service providers or
physical qualification. The existing domain table already covered installation,
configuration, draining, restart, replacement, removal, hub service changes and
reboot, so no duplicate list was added. Local links and edits were inspected;
no runtime tests were added or run for the prose corrections.
