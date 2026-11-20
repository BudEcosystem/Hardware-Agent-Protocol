# Owned finite I/O supervision:161 distinct checks pass

The [current source03](../implementation03/README.md) passes160pure checks and one
actual owned GPIO integration method. The latter captures all30cases for the
representative constant single-step candidate and independently inspects their
complete histories. It verifies private inputs before launch, exclusive owner
admission, actual attempt/run association, exact replay before and after reopening,
and changed-same-key refusal. The source02/03production is identical.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
| [attempt01-failed160](attempt01-failed160/README.md) |159pass /1errors |50.762|222 /2603729|
| [attempt02-passed160](attempt02-passed160/README.md) |160pass /0errors |50.451|222 /2603729|
| [attempt03-failed-setup](attempt03-failed-setup/README.md) |0pass /1errors |2.435|0 /0|
| [attempt04-passed160](attempt04-passed160/README.md) |160pass /0errors |49.855|222 /2603729|
| [attempt06-acquired-gpio](attempt06-acquired-gpio/README.md) |1pass /0errors |67.656|4269 /19309515|

The full test takes 67.656s including setup, image creation,
capture, archival, replay and independent inspection. The original60s supervisor/
group deadlines and180s test-parent deadline remain; this is not a timing benchmark
or wall-clock attestation. The archive verifies 3936output files,
14606609bytes. The256-file private image is3,918,651bytes with
the complete selected157-file dependency inventory. Raw acquisition retains
4,269files/19,309,515bytes under this separate supervisor integration's256MiB
acquisition scope; the pure harness remains16MiB, attempt reservation64MiB and
group-derived bound20MiB. None is an actual filesystem quota.

Read-only audits verify53unchanged databases and26case states with21activations,
11completions,10cancellations, zero claims and owners. The group accounts for
28operations, 44reserved admissions,
99ticks and 3832worker records. Failed challenge
completion objectives remain failed even when their expected fault response passes.
The initial validation error, unsafe fixture ancestor and acquisition-order mismatch
are retained with corrections. The completed worker was not rerun for acquisition.

This is isolated synthetic supervision, not public or physical qualification.
Trusted fixed service configuration, hard aggregate storage, supervised PWM,
I/O-specific owner-loss/interruption/limit failures and serialized public import
remain. The broader prompt-to-PAT learning, persistent Arduino applications,
real device/driver/intelligence-hub providers and microscope objective stays active.
