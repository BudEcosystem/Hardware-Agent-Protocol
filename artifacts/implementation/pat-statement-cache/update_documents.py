"""Publish current project notes only after successful runtime verification."""
import difflib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
runtime = json.loads((BASE / 'RUNTIME_RESULTS.json').read_bytes())
assert runtime['passed'] and runtime['tests'] == 861
changes = []
def save(name, before, after):
    assert before != after
    (ROOT / name).write_text(after)
    changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='previous/' + name, tofile='current/' + name))
def replace(name, old, new):
    before = (ROOT / name).read_text()
    assert before.count(old) == 1, name
    save(name, before, before.replace(old, new))
def prepend(name, paragraph):
    before = (ROOT / name).read_text()
    title, body = before.split('\n\n', 1)
    save(name, before, title + '\n\n' + paragraph + '\n\n' + body)

p = ROOT / 'README.md'; before = p.read_text()
start = before.index('The [PAT foundation is now integrated')
end = before.index('The [current worker diagnostic]', start)
latest = '''The [PAT foundation](artifacts/implementation/runtime-pat-foundation/README.md)
provides commit-time validation, compiler identity and static resource checks.
The new [statement-cache integration](artifacts/implementation/pat-statement-cache/README.md)
passes **nineteen catalog controls and the complete thirty-case worker → vault →
catalog → PAT application flow**. One simulated application completes once, with
original-key replay, configuration drift refusal and cold history intact.

The worker completes in about 57.7 seconds under the original 60-second limit;
the parent completes in 141.1 seconds under 180 seconds. The only production
change is a 256-statement authority Journal cache. That same edit is now in the
public runtime, where a new full run passes **all 861 original tests** with 161
stable inputs. The namespace qualification package remains isolated, and public
qualification, prompt learning and physical device/driver/hub providers remain
unfinished. One successful local run does not qualify deployment timing.

The preceding [local comparison](artifacts/verification/pat-statement-cache-evaluation/README.md)
passes 62 checks and observes 38.46% lower median capture CPU; this is not a
whole-worker speedup claim. The [binding review](research/host-contract/sqlite-cache-binding/README.md)
adds 4,025 fully read LF lines and records cursor/memory lifetime constraints.

'''
after = before[:start] + latest + before[end:]
after = after.replace('The main runtime\'s 861-test source is unchanged.',
    'That failed attempt remains retained; the later cache candidate above completes the same matrix.')
save('README.md', before, after)

prepend('docs/pat-foundation.md', '''The latest [statement-cache integration](../artifacts/implementation/pat-statement-cache/README.md)
passes the original thirty-case qualification, vault publication, catalog promotion
and one completed simulated PAT application, plus nineteen catalog controls.
The exact Journal cache setting is integrated into the public runtime; a new
861-test run preserves every prior test identity and all 161 input snapshots.
Public qualification installation and its storage-capacity requirements remain
unfinished. Earlier stage notes below retain their historical scope.''')
replace('docs/pat-foundation.md', '''authorizer refusals. Worker integration and the original full qualification gate
remain next; no public compiler or runtime source changes follow from this local
result alone.''', '''authorizer refusals. The full integration above supplies the subsequent worker
and public-runtime evidence; the local result alone did not authorize adoption.''')
replace('docs/pat-foundation.md', '''in the public runtime, and the existing full 861-test source is unchanged.''',
    '''in the public runtime. Its failed receipt is retained alongside the later successful candidate.''')

prepend('docs/prompt-to-pat.md', '''The latest [complete integration](../artifacts/implementation/pat-statement-cache/README.md)
passes all thirty qualification cases, publishes their evidence, promotes the
constructed PAT and completes one simulated application with original-key replay
and drift refusal. Nineteen catalog controls and the new full 861-test public
runtime check pass. This verifies another part of deterministic reuse; prompt
synthesis, experience-driven learning and persistent Arduino installation still
need implementation. Earlier stages retain their historical status below.''')
replace('docs/prompt-to-pat.md', '''a separate complete-worker integration candidate. Current PAT applicability,
evidence, public service installation and actual learning remain required.''',
    '''the subsequently completed integration above. Current PAT applicability,
evidence, public service installation and actual learning remain required.''')

prepend('docs/io-driver-hub-control.md', '''The latest [worker and runtime integration](../artifacts/implementation/pat-statement-cache/README.md)
passes the complete thirty-case simulated qualification-to-application flow and
a fresh full 861-test runtime run. It preserves the resource graph, current
binding checks and lifecycle boundaries while changing one Journal cache setting.
The protocol's device I/O, driver and intelligence-host providers remain required;
this simulated application does not physically qualify those providers. Earlier
stage notes below describe their original scopes.''')
replace('docs/io-driver-hub-control.md', '''authorization refusals. Its lower local CPU cost supports a separate worker
candidate; actual device, driver and hub providers still require implementation''',
    '''authorization refusals. The subsequent complete worker now passes; actual
device, driver and hub providers still require implementation''')

prepend('PROGRESS.md', '''Status: **active, incomplete — full statement-cache integration and public
regressions pass**. The preceding continuation made progress: it sealed the
62-check local cache evaluation and its full binding-source reading. The new
[integration](artifacts/implementation/pat-statement-cache/README.md) changes only
`cached_statements=256` on the authority Journal connection. Board connections,
capture SQL, guards, durability, the worker entry and the thirty-case matrix stay
unchanged. Two current test files receive recomputed identity expectations; all
other 301 candidate project files are exact. The source has 313 frozen inputs.

All **nineteen catalog controls pass** in their ten original bounded scopes.
The independent retained-state calculation opens 76 read-only databases under
99 original locks and verifies 1,149 files. These controls retain their declared
substituted semantic oracle. The separate actual run uses the real worker and
reducer, completes **all thirty cases**, publishes one vault manifest, promotes
one PAT and completes one simulated GPIO application. Original-key replay,
configuration drift refusal and cold vault/bridge history pass.

The worker finishes in **57.7 seconds** under its original 60-second limit; the
parent finishes in **141.1 seconds** under 180 seconds. The full-flow audit verifies
4,266 retained files, 267 image files, 57 original locks and four parent databases;
it opens no worker case database. All 4,011 vault references and 2,798 bodies join
the original request, publication, decision and single completed application.
One local pass does not establish deployment timing or the cause of prior failures.

The exact Journal edit is now applied to the public runtime. A fresh **861-test
run passes**, preserving the exact preceding test identities/order, all 161 stable
inputs and all 160 unchanged earlier inputs besides Journal. No second cache
benchmark or unchanged qualification attempt ran. Original failed namespace and
profiling attempts remain failed and retained. Review is by the primary agent;
no independent reviewer or physical execution is claimed.

[Next work](artifacts/implementation/pat-statement-cache/NEXT.md) prepares the
qualification-package integration while preserving the requirement for hard
aggregate storage limits, backed control continuation capacity, caps before
recovery and control-only recovery. Public qualification, native Harness
installation, prompt synthesis/learning, persistent MCU applications, actual
I/O/driver/hub providers, microscope commissioning and the remaining research and
home/laboratory/manufacturing scope remain unfinished.

## Earlier continuation: local statement-cache evaluation''')

replace('scripts/check_project_links.py',
    "        *ROOT.glob('artifacts/verification/pat-statement-cache-evaluation/*.md'),",
    "        *ROOT.glob('artifacts/implementation/pat-statement-cache/*.md'),\n"
    "        *ROOT.glob('artifacts/implementation/pat-statement-cache/implementation*/README.md'),\n"
    "        ROOT/'artifacts/implementation/pat-statement-cache/harness01/SCOPE.md',\n"
    "        *ROOT.glob('artifacts/verification/pat-statement-cache-evaluation/*.md'),")
replace('artifacts/implementation/pat-statement-cache/README.md',
    '''The same Journal edit has been applied to the public runtime; its full regression
verification is pending. The other 160 inputs to the previous 861-test receipt
were unchanged before the new run. The isolated qualification package is not yet
installed as a public qualification service.''',
    '''The same Journal edit is now verified in the public runtime: **all 861 tests
pass**, preserving the exact previous test identities and order, with 161 stable
input snapshots. Only Journal changed from the preceding receipt; the other 160
inputs remain exact. [Runtime verification](RUNTIME_RESULTS.json). The full-flow
audit predates this public edit; the runtime report records its later validation.
The isolated qualification package is not yet installed as a public service.''')
replace('artifacts/implementation/pat-statement-cache/NEXT.md',
    '# Complete public verification, then integrate the qualification boundary',
    '# Integrate the qualification boundary and continue device providers')
replace('artifacts/implementation/pat-statement-cache/NEXT.md',
    '''First finish and audit the new full public-runtime regression receipt. The only
public edit is the exact Journal connection option from the successful candidate.
Preserve all 861 test identities and all 161 input snapshots; resolve any actual
failure without overwriting receipts or weakening tests. No repeat local cache
benchmark or unchanged full worker is planned.''',
    '''The new full public-runtime regression receipt passes all 861 original tests
with 161 stable inputs. The only public edit is the exact Journal connection
option from the successful candidate. Preserve that receipt and its exact source
identity. No repeat local cache benchmark or unchanged full worker is planned.''')
with (BASE / 'documentation.patch').open('x') as out: out.write(''.join(changes))
print(json.dumps(dict(updatedDocuments=True, fullRuntimeTests=861, goalStatus='active')))
