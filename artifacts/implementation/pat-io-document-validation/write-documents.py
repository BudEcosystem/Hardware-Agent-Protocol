"""Record candidate acceptance limits and the sealed parameter reading overlay."""
import json
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-document-validation'
result = json.loads((B/'RESULTS.json').read_bytes())
assert result['distinctTestedMethods'] == 298 and result['canonicalControlsVerified']
assert result['reservedWorkerEndToEndVerified'] and result['postWorkerConfigurationSessionReplayVerified']
block = '''
The [canonical-document validation candidate]({prefix}artifacts/implementation/pat-io-document-validation/results/README.md)
passes **{passed} of 298 methods**, including all 286 controls. Its 19 new tests
check bounded exact-byte reuse while preserving current SQL reads, metadata
checks, dependency checks and durable publication. A 1,000-repeat observation
performs one full validation instead of 1,000; it establishes reduced validation
work in that fixture, without a deployment latency guarantee.

The reserved-worker scenario now completes all 30 cases and replays the original
attempt after configuration and session changes. Independent audits join its
reservation and all 37 input documents to the original request and worker.
{failed} other process methods retain failures, including original supervisor/group
deadlines and a retention scan that could not complete. Their
complete-group/later replay assertions are not claimed.
Every selected method ran once, with original bounds and all failed states
retained. This fresh result does not repair preceding failures.

The [next integration boundary]({prefix}artifacts/implementation/pat-io-document-validation/NEXT.md)
is durable supervisor-store identity and admission handoff. Protected control
capacity, serialized evidence import, configuration-aware promotion, public
mounting, prompt learning, persistent Arduino applications and actual
device/driver/hub providers remain open. The full HMS goal is active.
'''.format(prefix='{prefix}', passed=result['distinctPassingMethods'], failed=result['distinctFailingMethods'])
for name, prefix in [('docs/prompt-to-pat.md', '../'), ('docs/io-driver-hub-control.md', '../')]:
    path = ROOT/name
    text = path.read_text()
    assert 'canonical-document validation candidate' not in text
    path.write_text(text+'\n'+block.format(prefix=prefix))
path = ROOT/'PROGRESS.md'
text = path.read_text()
assert 'canonical-document validation candidate' not in text
anchor = '**Latest full regression passed:**'
assert text.count(anchor) == 1
text = text.replace(anchor, block.format(prefix='')+'\n'+anchor)
old = 'Combined retained SCPI coverage is 2,296 of 42,293 lines, still partial.'
assert text.count(old) == 1
text = text.replace(old, 'Combined retained SCPI coverage at that stage was 2,296 of 42,293 lines, still partial.')
text += '\nThe [SCPI parameter and coupling review](research/instrumentation/scpi-parameters-followup/README.md) adds all 484 LF lines and ten inspected PDF pages of Volume 1 Chapter 7. Combined coverage is now **2,780 of 42,293 LF lines**, still partial. It adds native rounding, numeric sentinel, relative-step, coupling and unit requirements for future driver bindings. The overlay is sealed separately; original sources/receipts remain unchanged and no instrument or acquired code was executed.\n'
path.write_text(text)

path = ROOT/'docs/io-driver-hub-control.md'
text = path.read_text()
anchor = '## One application across the graph'
assert text.count(anchor) == 1
addition = '''## Prompted applications and authority

The user supplies behavior, such as “monitor this sensor, drive this output
within these limits, and ask for a new strategy when the observed response falls
outside the supported range.” Installed endpoint firmware supplies the device
execution primitives; the user need not author an Arduino sketch. The agent
selects typed capabilities and proposes a bounded controller or PAT with explicit
input domains, state transitions, resource claims, stop conditions and evidence
requirements. Unsupported wiring, drivers or physical behavior must be resolved
before that application can run.

Experience can propose a new PAT or applicability rule. Repetition alone cannot
authorize promotion: validation must cover the declared domain and failure
behavior, and a versioned record must retain the supporting evidence. During
ordinary operation, a deterministic router checks current observations, freshness,
permissions, dependencies and resource availability. It invokes an eligible PAT
without model inference. Ambiguity, unsupported context or failed postconditions
produce a structured escalation; local qualified stop/fallback behavior remains
available while the agent is absent or deciding.

Device actions, driver administration and hub administration share the durable
operation lifecycle but have distinct permission scopes. A PAT that reads a sensor
or drives PWM does not thereby gain authority to replace a driver, change the
hub's network, install a model or reboot its host. A permitted administrative
operation names the verified artifact/configuration and affected dependencies;
the same registry makes its new generation visible to application applicability
checks. Any cross-domain sequence must preserve completed and unknown partial
effects, since these systems do not share one physical rollback transaction.

Determinism describes program selection and control flow for declared inputs.
Sensor values, inference outputs and physical responses still need observations
and bounded acceptance rules. The hub can host both inference and deterministic
execution, while the endpoint retains commissioned timing and outage behavior.
This application contract is proposed; persistent installation, learning and
physical providers remain implementation work.

'''
path.write_text(text.replace(anchor, addition+anchor))
path = ROOT/'artifacts/implementation/pat-io-document-validation/NEXT.md'
text = path.read_text()
text = text.replace('Both owner-loss methods still fail at original time limits and retain their partial state.',
                    'The owner-loss-after-settlement, owner-loss-after-spawn and configured/PWM worker methods still fail at original time limits. The archive-commit owner-loss method stops for SUPERVISOR_RETENTION_UNKNOWN. All partial state remains retained; exact outcomes appear in RESULTS.json.')
text += '\nThe retained archive-commit failure records a retention-scan refusal before its deadline. The collector catches a scan exception but does not retain its type/detail, so a disappearing journal, file mode issue, budget excess or other cause must not be inferred from the final tree alone. One transaction-bearing fixture remains uninspected and aggregate effects/claims/owners stay unknown. A future correction needs explicit evidence of the condition and bounded concurrent-retention semantics; do not simply ignore scan exceptions, recover the retained fixture or disable monitoring.\n'
path.write_text(text)
path = ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
path.write_text(path.read_text()+'\nThe [bounded canonical-document candidate](../pat-io-document-validation/results/README.md) passes all 286 controls and the complete reserved-worker/configuration/session replay scenario, with other original time-limit failures retained. Follow its [durable supervisor handoff plan](../pat-io-document-validation/NEXT.md); complete evidence import and public promotion remain open.\n')

path = ROOT/'research/instrumentation/README.md'
text = path.read_text()
old = 'bringing combined coverage to 2,296 of 42,293 lines. Its separate receipt preserves the earlier 1,696-line record and is not yet included in the consolidated corpus counts.'
assert text.count(old) == 1
text = text.replace(old, 'bringing that coverage to 2,296 lines. The [parameter follow-up](scpi-parameters-followup/README.md) adds 484 lines and ten visually reviewed pages, for **2,780 of 42,293 LF lines** combined. Both separate receipts preserve the original 1,696-line record; these overlays are not yet included in the consolidated corpus counts.')
path.write_text(text)
path = ROOT/'research/PLAN.md'
text = path.read_text()
old = 'combined coverage is 2,296/42,293 LF lines, still partial. The original reading record remains unchanged.'
assert text.count(old) == 1
text = text.replace(old, 'the [parameter follow-up](instrumentation/scpi-parameters-followup/README.md) adds all of Chapter 7, including three formulas and ten inspected PDF pages. Combined coverage is 2,780/42,293 LF lines, still partial. Original reading records remain unchanged.')
path.write_text(text)
path = ROOT/'docs/instrumentation-bindings.md'
text = path.read_text()
old = 'and [header follow-up](../research/instrumentation/scpi-headers-followup/README.md) together cover 2,296 of 42,293 LF lines.'
assert text.count(old) == 1
text = text.replace(old, ', [header follow-up](../research/instrumentation/scpi-headers-followup/README.md) and [parameter follow-up](../research/instrumentation/scpi-parameters-followup/README.md) together cover 2,780 of 42,293 LF lines.')
text = text.replace('reading-instrumentation.json) ,', 'reading-instrumentation.json),')
anchor = '## Stop and cancellation'
assert text.count(anchor) == 1
addition = '''The [parameter/coupling chapter review](../research/instrumentation/scpi-parameters-followup/NOTES.md) requires explicit quantization and accepted-value evidence. Native numeric inputs may be rounded; an out-of-range error does not establish preservation of the prior setting. Relative `UP`/`DOWN` operations and context-sensitive limits cannot be treated as idempotent absolute writes. Optional parameter forms must be advertised per command.

Native special numeric values need explicit quality classification: the chapter specifies large finite-looking encodings for infinity and NaN. A binding must preserve the native representation and distinguish these sentinels from ordinary measurements; it must not substitute zero or invalid JSON numbers. The chapter's range/NaN wording discrepancy and unspecified NaN cause remain unresolved without additional profile evidence.

Value/function coupling can change other settings, while an explicit setting may disable an automatic mode. `ONCE` returning to an off state is not proof that the requested action completed. Declare these affected resources and resulting modes in the operation contract. Units, reference impedance and peak/peak-to-peak/RMS conventions belong to the binding and evidence; a driver must not guess waveform conversions or collapse ratios, percentages and logarithmic differences into one unit.

'''
path.write_text(text.replace(anchor, addition+anchor))
path = ROOT/'scripts/check_project_links.py'
text = path.read_text()
anchor = "        *ROOT.glob('artifacts/implementation/pat-io-service-runs/*.md'),"
assert text.count(anchor) == 1
extra = '\n'.join('        '+line for line in [
    "*ROOT.glob('artifacts/implementation/pat-io-document-validation/*.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-document-validation/implementation*/README.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-document-validation/harness*/README.md'),",
    "*ROOT.glob('artifacts/implementation/pat-io-document-validation/harness*/SCOPE.md'),",
    "ROOT/'artifacts/implementation/pat-io-document-validation/results/README.md',",
    "*ROOT.glob('artifacts/implementation/pat-io-document-validation/results/*/README.md'),",
    "*ROOT.glob('research/instrumentation/scpi-parameters-followup/*.md'),"])
path.write_text(text.replace(anchor, extra+'\n'+anchor))
print(json.dumps(dict(stagePassing=result['distinctPassingMethods'], stageSelected=298, scpiCoveredLines=2780, fullGoal='active')))
