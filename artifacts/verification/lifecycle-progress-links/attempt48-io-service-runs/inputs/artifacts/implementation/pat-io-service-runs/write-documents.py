"""Publish exact stage status and the independently sealed SCPI reading overlay."""
import json
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-service-runs'
result = json.loads((B/'RESULTS.json').read_bytes())
assert result['distinctTestedMethods'] == 279 and result['reservationControlsVerified']
assert result['reservedWorkerEndToEndVerified'] is False
passed = result['distinctPassingMethods']
block = '''
The [durable I/O run reservation stage]({prefix}artifacts/implementation/pat-io-service-runs/results/README.md)
passes **{passed} of 279 distinct methods**. All 267 control methods pass,
including 29 new reservation controls. The new reserved-worker method reaches
its unchanged 60-second deadline in both ordinary and passive diagnostic
attempts; its later configuration/session-change replay assertions are
unreached. Two inherited owner-loss methods also fail: one lacks a complete
return after a recorded supervisor deadline; the other returns a failed group
at its own wall-time limit. All selected methods were executed and all failures
remain retained.

The authority atomically commits the original run intent, request, receipt and
complete input bundle. Exact replay retrieves those inputs across source,
configuration and session drift, subject to current authorization and retained
state integrity. Independent audits join both failed workers to the original
reservation and all 37 input documents each. Reservation is not proof of
execution. Passive CPU/pressure observations do not establish the cause of the
deadline or provide a deployment capacity guarantee.

The [next integration boundary]({prefix}artifacts/implementation/pat-io-service-runs/NEXT.md)
must pin a durable supervisor authority and retain the original attempt
association before launch. A replacement or missing supervisor store must not
cause an existing run to execute again. Deadline diagnosis, protected hub
compute/storage capacity, serialized evidence import, configuration-aware
promotion and public service mounting remain open. Prompt learning, persistent
Arduino controllers and real device/driver/hub providers remain required.
The full HMS goal is active.
'''
for name, prefix in [('docs/prompt-to-pat.md', '../'), ('docs/io-driver-hub-control.md', '../')]:
    path = ROOT/name
    text = path.read_text()
    assert 'durable I/O run reservation stage' not in text
    if name == 'docs/prompt-to-pat.md':
        old = 'The complete I/O qualification\nworker and independent outcome oracle still need implementation;'
        assert text.count(old) == 1
        text = text.replace(old, 'That fixed-unit stage did not include the I/O qualification\nworker or independent outcome oracle; later implementations and their acceptance\nlimits are recorded below. At that stage,')
    else:
        anchor = '## Resource and capability domains'
        assert text.count(anchor) == 1
        diagram = '''The required flow connects learning and deterministic execution to all three
control domains. Qualification, provider mounting and physical support have the
implementation limits recorded below.

```mermaid
flowchart TD
    Prompt[Prompt or unfamiliar context] --> Agent[Agent planning]
    Agent --> Candidate[Typed plan and PAT candidate]
    Candidate --> Qualification[Validation and qualification]
    Qualification --> Catalog[PAT catalog]
    Context[Observed context] --> Router[Deterministic applicability checks]
    Catalog --> Router
    Router -->|Eligible PAT| Runtime[Durable execution runtime]
    Router -->|New or unsupported situation| Agent
    Runtime --> Device[Device I/O and bus providers]
    Runtime --> Hub[Hub compute and storage providers]
    Runtime --> Lifecycle[Driver and service lifecycle providers]
    Device --> Evidence[Receipts and observations]
    Hub --> Evidence
    Lifecycle --> Evidence
    Evidence --> Context
    Evidence --> Qualification
```

Each PAT declares its resource use and dependencies across these domains.
Driver or hub changes can invalidate applicability. The agent handles novelty;
installed deterministic controllers and local failure responses continue under
their qualified device-specific limits.

'''
        text = text.replace(anchor, diagram+anchor)
    path.write_text(text+'\n'+block.format(prefix=prefix, passed=passed))
path = ROOT/'PROGRESS.md'
text = path.read_text()
anchor = 'The [authority-owned I/O configuration stage]'
assert text.count(anchor) == 1
text = text.replace(anchor, block.format(prefix='', passed=passed)+'\n'+anchor)
text += '\nThe separate [SCPI header reading overlay](research/instrumentation/scpi-headers-followup/README.md) adds 600 LF lines and all twelve PDF pages of Volume 1 Chapters 5–6. Combined retained SCPI coverage is 2,296 of 42,293 lines, still partial. The original receipt remains unchanged. Native parser state, partial compound-command effects and query exceptions constrain future driver/session bindings; no instrument or acquired code was executed.\n'
path.write_text(text)
path = ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
path.write_text(path.read_text()+'\nThe [run-reservation stage](../pat-io-service-runs/results/README.md) adds immutable original inputs and 29 passing controls, but its new worker/replay method still fails at the original deadline. Continue with [deadline diagnosis and durable supervisor handoff](../pat-io-service-runs/NEXT.md); no public mounting or promotion claim follows.\n')

path = ROOT/'research/instrumentation/README.md'
text = path.read_text()
old = 'SCPI-99 remains partial at 1,696 of 42,293 lines.'
assert text.count(old) == 1
path.write_text(text.replace(old, 'SCPI-99 remains partial: the [header follow-up](scpi-headers-followup/README.md) adds 600 lines and twelve visually reviewed PDF pages, bringing combined coverage to 2,296 of 42,293 lines. Its separate receipt preserves the earlier 1,696-line record and is not yet included in the consolidated corpus counts.'))
path = ROOT/'research/PLAN.md'
text = path.read_text()
old = '8. Finish SCPI-99, Modbus security, actual instrument manuals and transport standards.'
assert text.count(old) == 1
path.write_text(text.replace(old, old+' The [SCPI header follow-up](instrumentation/scpi-headers-followup/README.md) now covers complete Volume 1 Chapters 5–6, including both syntax diagrams and all twelve pages; combined coverage is 2,296/42,293 LF lines, still partial. The original reading record remains unchanged.'))
path = ROOT/'docs/instrumentation-bindings.md'
text = path.read_text()
old = 'SCPI remains selected-only in [the original reading ledger](../research/instrumentation/reading-instrumentation.json).'
assert text.count(old) == 1
text = text.replace(old, 'SCPI remains selected-only: the [original reading ledger](../research/instrumentation/reading-instrumentation.json) and [header follow-up](../research/instrumentation/scpi-headers-followup/README.md) together cover 2,296 of 42,293 LF lines.')
addition = '''
The [complete header-chapter review](../research/instrumentation/scpi-headers-followup/NOTES.md) further constrains native dispatch. Default nodes do not alter the parser's remembered path, so omitting a node can change a later relative command. A compound message can execute an earlier command before rejecting a later header; syntax failure does not establish rollback. Providers should validate the complete typed sequence, generate supported native forms and serialize the command/response session. Those measures cannot make physical effects atomic or resolve a lost reply.

A query marker does not establish a read-only operation: measurement queries have explicit exceptions, and status/error operations need their own consumption semantics. Declare actual effects, units and coupling dependencies in the capability contract. Keep electrical ports, independent capabilities and separately addressed logical instruments distinct; the latter have separate buffers and status models despite shared physical infrastructure. Do not append a numeric suffix indiscriminately, since a single-capability instrument need not accept one.

'''
# Place the new requirements after the existing SCPI discussion, before the next section.
start = text.index('## SCPI session requirements')
end = text.find('\n## ', start+4)
assert end != -1
text = text[:end]+'\n'+addition+text[end:]
path.write_text(text)

path = ROOT/'scripts/check_project_links.py'
text = path.read_text()
anchor = "        *ROOT.glob('artifacts/implementation/pat-io-service-authority/*.md'),"
assert text.count(anchor) == 1
extra = '\n'.join('        '+line for line in [
    "*ROOT.glob('artifacts/implementation/pat-io-service-runs/*.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-service-runs/implementation*/README.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-service-runs/harness*/README.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-service-runs/harness*/SCOPE.md'),",
    "ROOT/'artifacts/implementation/pat-io-service-runs/results/README.md',",
    "*ROOT.glob('artifacts/implementation/pat-io-service-runs/results/*/README.md'),",
    "ROOT/'research/instrumentation/README.md',",
    "*ROOT.glob('research/instrumentation/scpi-headers-followup/*.md'),"])
path.write_text(text.replace(anchor, extra+'\n'+anchor))
print(json.dumps(dict(stagePassing=passed, stageSelected=279, scpiCoveredLines=2296, fullGoal='active')))
