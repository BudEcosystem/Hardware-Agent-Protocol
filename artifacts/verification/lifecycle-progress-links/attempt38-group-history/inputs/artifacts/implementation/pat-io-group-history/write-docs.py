"""Reconcile complete historical inspection with incomplete current acceptance."""
from pathlib import Path

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-group-history'
assert not (B / 'results/index.json').exists(), 'Sealed stage must not be rewritten'

path = ROOT / 'PROGRESS.md'
text = path.read_text().replace('The current [encoding stage]', 'The preceding [encoding stage]')
start = text.index('Complete capture is now available for both finite synthetic groups.')
end = text.index('The separate [qualification supervisor rebase]', start)
text = text[:start] + '''The current [group-history stage](artifacts/implementation/pat-io-group-history/results/README.md)
passes **108 distinct methods**: 107 pure setup/boundary checks on source04 and
one complete retained-history/adversary method. The independent reader checks
all 30 source01 GPIO cases, including all 25 fixed challenges, against separately
retained pre-run setup. It derives nominal completion and negative outcomes,
dispatches every complete challenge reader, checks exact archive closure and
recomputes operation, tick, record and byte accounting. It rejects false aggregate
accounting, an unreported file, a forged nominal report and changed trusted
authority. File, SQL and clock access are forbidden during inspection.

The historical group contains 28 operations, 99 ticks, 3,832 charged records and
14,660,708 derived bytes. The 30 case inspections total 216,187 bytes, with a
separate bounded summary. Its 70.718-second method includes successful inspection
and four adversarial inspections; this is not a single-pass benchmark. Two
wrapper corrections handle explicitly unavailable current bindings after
authority loss and the four-actor resource environment. Their original failed
attempts, a source-selector refusal before child creation and all original
subject/setup bytes remain retained.

Fresh current acceptance remains incomplete. Source02 GPIO/PWM captures stop
after 20/24 cases at the unchanged 60s deadline. The fresh corrected source04
GPIO run stops after 24 cases and never reaches inspection. Its active
permission-pending case retains a failed child and canceled receipt, but the
parent remains running. Zero endpoint claims/owners does not establish complete
settlement. Source04 PWM harness14 is prepared but unexecuted after that gate
fails. No source of the timing variation has been established.

Every started attempt retains matched origins, stable project/frozen/harness
inputs and 159 external pins, unchanged within-attempt compiler/driver identities,
and complete original raw output plus copies. The latest source contains 225
inherited files, one retained test and 3972 immutable historical fixture files.
Review is by the primary agent; existing helpers remain usage-limited. Live HMS
and the adjacent Harness are unchanged. Historical inspection sets no deployment,
run, wall-time, physical, hard-quota or qualification attestation flags.

The next work is complete current-source capture and inspection within the
original limits, followed by trusted process/run association and actual aggregate
storage/supervision before public qualification. Public PAT tools, agent learning,
persistent Arduino applications and physical device/driver/intelligence-hub
providers remain unfinished. The complete end-to-end goal stays active.

''' + text[end:]
path.write_text(text)

path = ROOT / 'docs/prompt-to-pat.md'
text = path.read_text()
start = text.index('The [current encoding stage]')
end = text.index('An operator says, for example,', start)
text = text[:start] + '''The [group-history stage](../artifacts/implementation/pat-io-group-history/results/README.md)
passes 108 distinct methods and independently checks a complete retained 30-case
GPIO group against separate pre-run setup, including all 25 fixed challenges,
nominal completion, negative outcomes and exact archive accounting. Four forged
archive/setup variations refuse. This completes historical semantic composition.

Fresh current acceptance remains incomplete: source02 GPIO/PWM stop after 20/24
cases, and corrected source04 GPIO stops after 24 at the unchanged capture
deadline. Its active parent remains running despite a failed child and canceled
receipt. Source04 PWM is unexecuted. Complete current capture and inspection,
trusted process/run association and actual aggregate enforcement remain required
before a learned PAT can be qualified or promoted. Historical inspection does
not attest deployment, physical behavior or current-run identity.

''' + text[end:]
path.write_text(text)

path = ROOT / 'docs/io-driver-hub-control.md'
text = path.read_text()
start = text.index('The [current encoding stage]')
old = text[start:]
assert old.endswith('qualification are still required.\n')
text = text[:start] + '''The [group-history stage](../artifacts/implementation/pat-io-group-history/results/README.md)
passes 108 distinct methods and independently verifies all 30 cases in a retained
GPIO group, including the shared pin/PWM/alias challenge and all 25 fixed
challenges. Separate pre-run setup, complete outcomes and archive accounting
are checked without file, SQL or clock access during inspection.

The fresh corrected GPIO run stops after 24 cases at the original deadline;
its active parent remains running despite a failed child and canceled receipt.
The corrected PWM run is unexecuted. Historical verification does not supply
current process/run attestation, hard aggregate quotas or physical driver and
intelligence-hub lifecycle qualification. Those requirements and complete fresh
current capture/inspection remain open.
'''
path.write_text(text)

path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
text = path.read_text()
lines = text.splitlines()
matches = [i for i, line in enumerate(lines) if line.startswith('| Group budgets and retained evidence |')]
assert len(matches) == 1
lines[matches[0]] = '| Group budgets and retained evidence | The [group-history stage](../pat-io-group-history/results/README.md) passes 108 distinct methods and independently verifies all 30 cases of a retained source01 GPIO group against separate pre-run setup, including all 25 fixed challenges and exact archive accounting | Corrected source04 fresh GPIO stops after 24 cases at the unchanged deadline; its active parent remains running. Source04 PWM is unexecuted. Complete fresh capture/inspection, trusted process/run association and actual aggregate enforcement remain required |'
text = '\n'.join(lines) + '\n'
start = text.index('The closed combined matrix and preflight now exist')
end = text.index('Finite I/O qualification still does not implement', start)
text = text[:start] + '''The closed combined matrix, preflight and complete historical semantic
composition now exist as isolated libraries. The corrected reader independently
checks a complete retained 30-case GPIO group against separate pre-run setup;
all 25 fixed challenges, nominal completion, negative outcomes and exact archive
accounting pass. The original encoding stage's complete GPIO/PWM captures remain
historical results.

Current acceptance is incomplete. Source02 GPIO/PWM capture only 20/24 cases;
corrected source04 GPIO captures 24 before the unchanged deadline and does not
reach inspection. Its active parent remains running despite a failed child and
canceled receipt. Source04 PWM is unexecuted. The next work completes fresh
current-source capture and inspection within the original limits, then adds
trusted process/run association and actual aggregate storage/supervision before
public qualification. Historical semantic agreement does not attest the current
deployment, run, wall time or physical behavior. All failed attempts remain.

''' + text[end:]
path.write_text(text)
print('Reconciled four documents; historical inspection passes, current acceptance remains incomplete.')
