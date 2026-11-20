"""Reconcile complete synthetic capture with remaining qualification work."""
from pathlib import Path

ROOT = Path.cwd()
path = ROOT / 'PROGRESS.md'
text = path.read_text()
start = text.index('The new [group efficiency stage]')
end = text.index('The separate [qualification supervisor rebase]', start)
text = text[:start] + '''The preceding [group efficiency stage](artifacts/implementation/pat-io-group-efficiency/results/README.md)
passed 95 distinct methods and first completed all 30 GPIO cases. Exact validated
input reuse and compact fresh stores preserve authority, numeric types, standalone
validation, recovery and replay. Its full PWM attempt stopped after 28 cases at
the original deadline; that failure and the separate diagnostic profile remain.
The profile identified duplicate encoding in evidence writes and topology
snapshots.

The current [encoding stage](artifacts/implementation/pat-io-encoding/results/README.md)
passes **99 distinct methods**, including **both complete 30-case GPIO and PWM
groups**. Three production files remove duplicate encoding without adding a
cache, changing SQL queries, skipping validation or relaxing any limit. The
configured writer stores its existing exact envelope after the original combined
reservation and wall/group check. Topology snapshots reuse the canonical bytes
that produced the detached, strictly checked tree. Nine focused methods verify
exact bytes/references, both streams, inherited profiles, changed inputs, reuse,
budget precedence and retained exclusive-create/fsync failures. The original 87
selected checks and three actual group methods remain unchanged.

GPIO passes in 50.940 test seconds and PWM in 51.932, under the original 60s group
deadline. Each covers all 25 fixed challenges plus five candidate cases, with
28 actual child operations, 44 reserved admissions, 99 ticks and 3,832 charged
records. GPIO retains 14,606,609 raw bytes; PWM retains 14,821,081. Producer/derived
accounting is 10,149,988/14,660,708 bytes for GPIO and 10,289,708/14,875,180 for PWM.
Each group preserves 26 states and 52 databases. Read-only endpoint audits find
21 activations, 11 completions, 10 cancellations and zero claims/owners in each.
All databases pass integrity checks with unchanged hashes. SQLite allocations
are 4,510,720 bytes for GPIO and 4,585,472 for PWM. These single-run observations
are not benchmarks, hard-real-time guarantees or physical power-loss evidence.

The actual 250-record cutoff passes and retains the same 977,425 raw bytes as the
preceding stage. All four attempts retain stable 222 project files, 225 frozen
entries, six active harness inputs and 159 external pins, matched executed
origins and unchanged within-attempt compiler/driver identities. All originals
and complete copies remain. Pre-execution review corrected an inherited target
literal in a fresh harness; the original unexecuted preparation is retained.
Review is by the primary agent; existing helpers remain usage-limited. Live HMS
and the adjacent Harness are unchanged.

Complete capture is now available for both finite synthetic groups. The next
implementation composes independent outcomes against trusted current setup and
run association, then enforces actual aggregate storage and supervision before
public qualification. Endpoint state observations are not complete-history
proof. Public PAT tools, agent learning, persistent Arduino applications and
physical device/driver/intelligence-hub providers remain unfinished. The complete
end-to-end goal stays active.

''' + text[end:]
path.write_text(text)

path = ROOT / 'docs/prompt-to-pat.md'
text = path.read_text()
start = text.index('The [current group efficiency stage]')
end = text.index('An operator says, for example,', start)
text = text[:start] + '''The [current encoding stage](../artifacts/implementation/pat-io-encoding/results/README.md)
passes 99 distinct checks and completes all 30 cases for both GPIO and PWM under
the original limits. Removing duplicate evidence/topology encodings preserves
exact records, validation, authority checks, recovery, durability and accounting.
The preceding PWM deadline failure remains retained. GPIO and PWM pass in 50.940
and 51.932 test seconds; these are single-run observations. The next step is
independent current-group outcome composition, trusted setup/run association and
actual aggregate enforcement. Complete capture alone cannot qualify or promote
a learned PAT.

''' + text[end:]
path.write_text(text)

path = ROOT / 'docs/io-driver-hub-control.md'
text = path.read_text()
old = '''The [current group efficiency stage](../artifacts/implementation/pat-io-group-efficiency/results/README.md)
passes 95 distinct checks and completes all 30 GPIO cases, including the shared
pin/PWM/alias challenge, within the original capture limits. Exact plan reuse and
compact fresh SQLite stores retain runtime authority, durability settings and
recovery behavior. Full PWM still reaches only 28 of 30 cases before its deadline;
the failed attempt remains. Independent outcomes, actual aggregate quotas and
physical driver/intelligence-hub lifecycle qualification are still required.
'''
new = '''The [current encoding stage](../artifacts/implementation/pat-io-encoding/results/README.md)
passes 99 distinct checks and completes all 30 cases for both GPIO and PWM,
including the shared pin/PWM/alias challenge, under the original capture limits.
Duplicate evidence/topology encoding is removed while exact records, authority,
validation, durability settings and recovery remain. Each complete group retains
26 states and 52 databases; endpoint audits find no claims or owners. Earlier
deadline failures remain. Independent outcomes, trusted setup/run association,
actual aggregate quotas and physical driver/intelligence-hub lifecycle
qualification are still required.
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))

path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
text = path.read_text()
lines = text.splitlines()
matches = [i for i, line in enumerate(lines) if line.startswith('| Group budgets and retained evidence |')]
assert len(matches) == 1
lines[matches[0]] = '| Group budgets and retained evidence | The [encoding stage](../pat-io-encoding/results/README.md) passes 99 distinct checks, including the actual 250-record cutoff and complete 30-case GPIO/PWM captures in 50.940/51.932 test seconds under unchanged limits | Compose independent outcomes against trusted current setup/run association. Exact records, fsync, guards and ceilings remain; complete capture and closed-state accounting do not impose a hard aggregate filesystem quota. Actual enforcement remains required |'
text = '\n'.join(lines) + '\n'
start = text.index('The closed combined matrix and preflight now exist')
end = text.index('Finite I/O qualification still does not implement', start)
text = text[:start] + '''The closed combined matrix and preflight now exist as an isolated library.
All 25 named fixed challenges have staged capture and independent outcome
components. Both GPIO and PWM now complete all 30 cases under the original bounds.
The duplicate-encoding correction preserves exact evidence and durability; the
preceding failures remain retained. The next implementation joins independently
computed semantic outcomes with trusted current setup and run association, then
enforces actual aggregate storage before public qualification or promotion.
Captured cases and endpoint state observations do not substitute for those
independent semantic and deployment checks. No additional performance change is
needed to explain the current capture result.

''' + text[end:]
path.write_text(text)
print('Reconciled four current progress/design documents; full goal remains active.')
