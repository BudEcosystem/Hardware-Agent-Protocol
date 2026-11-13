# SQLite authorizer follow-up

Two official pages were browsed, downloaded with a 1 MiB/20-second per-response bound, and fully read as extracted API-body text: 80 + 56 LF lines, including the signature and all 33 action-code rows. Navigation/scripts were excluded from extraction; raw bytes remain retained. Linked pages were not acquired/read. There are no meaningful body images. HTTP dates/ETags identify these responses, not a pinned SQLite library release. No acquired program or SQLite test was executed.

An authorizer belongs to one connection and runs during statement compilation. Re-preparation during stepping can invoke it again, so the appropriate callback must remain installed. Ordinary evaluation does not repeatedly authorize the prepared statement. Generated-column expressions have a separate schema-parsing caveat. Only one authorizer is installed; replacement or disabling changes that connection's guard. Its callback cannot prepare/step on that same connection. `SQLITE_IGNORE` is not a general refusal: ignored reads substitute NULL; ignored DELETE still deletes rows. Use denial for prohibited effects. [Compile-Time Authorization Callbacks](https://www.sqlite.org/c3ref/set_authorizer.html)

The action table includes transaction/savepoint control, attachment, pragmas, DDL, virtual tables and function calls as well as DML/reads. Auxiliary arguments can be absent, and their meaning depends on the action; function name is the fourth C callback argument. Database and inner trigger/view attribution matter. Identifier comparison must account for arbitrary case. [Authorizer Action Codes](https://www.sqlite.org/c3ref/c_alter_table.html)

HMS implications and proposed checks, not executed findings:

- Prepare/cache a write while permitted, enter the callback guard, then reuse identical SQL on the same connection. Verify refusal and unchanged durable rows/transaction state. Repeat with parameters, transactions/savepoints and post-guard legitimate work. Changing only a Python guard flag is not evidence that cached statements are re-authorized.
- If the implementation depends on statement-cache disabling or callback replacement invalidating prepared statements, test the exact deployed Python/SQLite combination; these two C API pages do not establish that integration behavior.
- Test nested guard entry, exceptions and restoration, NULL/empty callback arguments, case variation, trigger/view paths, and default refusal of unrecognized actions. Preserve the existing authorizer deliberately; avoid silently replacing another guard.
- Treat this as protection against accidental SQL misuse by trusted callbacks. Code retaining the connection can replace the authorizer, use another connection or perform non-SQL effects. Function callbacks and external I/O need their own trust boundaries. An authorizer is neither a Python sandbox nor a CPU/memory/disk deadline mechanism.

Full reading applies only to these two pages. Corpus integration and broader SQLite/host-contract research remain open.
