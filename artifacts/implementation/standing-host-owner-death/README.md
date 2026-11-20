# Standing host owner-death source candidate

**Source prepared, unexecuted.** This isolated increment implements all thirteen
cuts in the sealed owner-death design against the exact tested freeze07 host
closure. It changes no production, public baseline, or sealed parent bytes.
No candidate import, build, process launch, signal, or control execution occurred
during source preparation.

The inner parent keeps one actual native endpoint alive across each host owner's
intentional death and a fresh recovery owner. Only the parent controls native
ticks. The original qualification bundle and native image are consumed at their
original absolute host-attempt04 paths; copied evidence is audit-only. Existing
20-case/173-check living-owner evidence is the prerequisite, not substituted by
this new harness.

Read [PLAN.md](PLAN.md), [REVIEW-NOTES.md](REVIEW-NOTES.md), source-pins.json and
SOURCE-REVIEW.json before execution review. owner_death_controls.py and
run_checks.py are the only new executable sources. The expected complete success
is thirteen cases, 39 joined inner reaps (13 native exit0, 13 owner SIGKILL,
13 recovery exit0), and one outer exit0/reap. No actual owner-death evidence is
claimed until the reviewed bounded run and its retained joins pass.

This is still a fixed synthetic native profile. It does not qualify partial-frame
or in-transaction death, power loss, storage exhaustion, guardian loss, physical
I/O, GPU services, a public runtime mount, protected capacity or broad PAT domains.
