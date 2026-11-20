# Finite I/O trial phase engine candidate

This isolated candidate adds an original phase engine and 20 integration methods
over the actual `IoRuntime`, trusted PAT resolver, compiler, procedure manager and
shared GPIO/PWM board. All 157 inherited project files remain unchanged from the
passing timing candidate. This is a worker component, not a complete qualification
service or independent outcome reducer.

The engine validates trusted setup before creating one fresh runtime inside an
existing empty private directory. It compiles one immutable request, drains durable
progress at each virtual time, and advances only to retained due/start/lease/run/
completion events. Refresh counters are excluded from progress. Exact parent replay
retains request and operation identities. Reopening never changes the compiled
request to the board's new session.

Raw typed pages cover board resources/owners/fences/effects/receipt versions and
selected authority execution, replay, procedure and retained configuration tables.
Checkpoints hold hashes/references to those pages with phase and clock records.
Captured pages are reused by content; call records preserve their order. Tables,
rows, cells, records, bytes, ticks and cooperative wall time have fixed bounds.
Large records or exhausted evidence capacity refuse rather than omit rows. Full
original databases and every record remain in the private trial directory.

The planned tests distinguish completed cycles from canceled activations, retain
unknown effects after receipt loss, and exercise sixteen steps. A source finding
changes the recovery cases from the fan worker: I/O owner reopen rotates session.
An accepted child or an unstarted suffix cannot resume under its old session;
a completed single-step history can still reconcile and finish. No silent rebind
or new-key mutation retry is added.

Every engine report has `qualificationPassed: false` and
`independentOutcomeChecked: false`. Closing does not establish idle. Failed and
unresolved state is retained. Matrix orchestration, required fault/challenge
composition, independent raw-evidence reduction, public installation, aggregate
storage supervision and actual-device qualification remain required work.

Preparation is source-only. Actual execution, if released, is retained separately.
No live runtime files, user state, adjacent Harness checkout or hardware are changed.
