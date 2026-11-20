# Initial timing captures: two verifier failures per primitive

The GPIO selection ran nine methods in 58.133 seconds: seven passed and two
errored. The PWM selection ran eight methods in 54.241 seconds: six passed and
two errored. Both attempts remain **failed**, with complete original raw state
and copied evidence retained under the original 180-second/16 MiB limits.

The start-deadline-equality and lease-equality captures both stopped before
handoff: no board activation, dispatch link or board receipt, and no retained
claim. Their authority events correctly say `start_or_lease_expired`. The
configuration checker incorrectly assumed every `rejected_before_dispatch`
event required lost invoke permission, producing
`PAT_IO_CONFIGURATION_REFUSAL_CAUSE`. The operation fold already supports this
expiry event; runtime/provider behavior was not changed.

The [proof](proof.json) rechecks both source/harness pins, all actual methods,
origins, before/after inventories, 32 exact database paths and paired raw records.
It acquires 8,248 GPIO attempt files and 8,247 PWM attempt files. Original raw
directories and identities are recorded there: 1,144 files/6,531,662 bytes and
1,143 files/6,682,209 bytes respectively. No failed result is relabeled passing.

The [corrected source](../../implementation02/README.md) extends only the
independent configuration/refusal checks and adds rehashed expiry attacks.
It preserves the worker, underlying runtime and original limits. A separate
launcher-preparation syntax error was caught by AST parsing before project
execution; its rejected text remains in the stage preparation diagnostics.
Full candidate matrix qualification, physical providers and hub control remain
unfinished.
