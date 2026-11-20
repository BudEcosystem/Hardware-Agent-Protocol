"""Record the verified installed-library result in current project documents."""
import difflib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
result = json.loads((BASE / 'RUNTIME_RESULTS.json').read_bytes())
assert result['passed'] and result['tests'] == 866 and result['stableInputs'] == 244
patch = []
def save(name, before, after):
    assert before != after
    (ROOT / name).write_text(after)
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='previous/' + name, tofile='current/' + name))
def replace(name, old, new):
    before = (ROOT / name).read_text()
    assert before.count(old) == 1, name
    save(name, before, before.replace(old, new))
def prepend(name, text):
    before = (ROOT / name).read_text(); title, body = before.split('\n\n', 1)
    save(name, before, title + '\n\n' + text + '\n\n' + body)

name = 'README.md'; before = (ROOT / name).read_text()
needle = 'The [PAT foundation](artifacts/implementation/runtime-pat-foundation/README.md)'
assert before.count(needle) == 1
text = '''The [qualification libraries are installed in the main project](artifacts/implementation/runtime-qualification-package/README.md):
40 additional host modules and 42 package files retain the exact qualified source.
The installed identity inspection matches the successful candidate, including its
267-file worker image. A new full public run passes **866 tests**, preserving all
861 prior tests and adding five original vault commit checks, with **244 stable
inputs** including native C and binary files. [Library guide](docs/qualification-libraries.md).
Public qualification/PAT service mounting, prompt learning and physical providers
remain unfinished; the native supervisor retains its explicit host/ABI profile.

'''
after = before.replace(needle, text + needle)
old = '''public runtime, where a new full run passes **all 861 original tests** with 161
stable inputs. The namespace qualification package remains isolated, and public
qualification, prompt learning and physical device/driver/hub providers remain
unfinished. One successful local run does not qualify deployment timing.'''
new = '''public runtime, where the preceding full run passed **861 tests** with 161
stable inputs. The subsequent library installation above extends that coverage.
Public qualification, prompt learning and physical device/driver/hub providers
remain unfinished. One successful local run does not qualify deployment timing.'''
assert after.count(old) == 1
save(name, before, after.replace(old, new))

prepend('docs/pat-foundation.md', '''The [qualification-library installation](../artifacts/implementation/runtime-qualification-package/README.md)
brings the complete verified finite-I/O host modules and explicit qualification
package into the main project without changing their bytes. Installed identities
match the successful candidate; all 866 public tests pass, including five original
held-vault commit checks and all 861 previous tests. Runtime receipts now capture
244 inputs, including the native binary and C source. Public service ownership,
storage enforcement and PAT tool mounting remain unfinished. [Installed guide](qualification-libraries.md).''')
prepend('docs/prompt-to-pat.md', '''The [installed qualification libraries](qualification-libraries.md) now provide
the verified worker, reduction, vault, publication and deterministic catalog code
in the main project. All 866 public tests pass; five added checks preserve the
held-evidence requirement through admission commit. This supplies implementation
for the qualification boundary. The owned public service, prompt synthesis,
experience-driven learning and persistent Arduino installation remain unfinished.''')
prepend('docs/io-driver-hub-control.md', '''The [qualification libraries](qualification-libraries.md) are now installed in
the main project with the same identities as the successful simulated worker.
All 866 public tests pass. Existing device/driver/hub resource contracts and
public methods are unchanged; concrete providers still need implementation and
physical qualification. The native supervisor's explicit host/ABI profile does
not establish portability or timing on another intelligence hub.''')
prepend('docs/control-storage.md', '''The [qualification-library installation](qualification-libraries.md) now places
the verified vault and publication code in the main project. Five original
held-vault commit checks join the public suite, which passes all 866 tests.
This preserves evidence validity through commit; it does not add aggregate
storage enforcement or backed control capacity. Public qualification mounting
still requires the complete storage and recovery profile described here.''')
prepend('PROGRESS.md', '''Status: **active, incomplete — qualification libraries installed; 866 public
tests pass**. The preceding turn made verified progress: the full thirty-case
simulated qualification-to-PAT flow and all 861 public runtime tests passed.
The new [library installation](artifacts/implementation/runtime-qualification-package/README.md)
copies 40 missing host modules and 42 qualification-package files byte-for-byte
from that sealed candidate. All 43 existing host modules and seven schemas remain
exact. Public Runtime/CLI/MCP methods and default startup behavior are unchanged.

The installed import inspection exactly matches the candidate identity report:
39 origins, 17 poisoned legacy names, four initializer-drift refusals and a
267-file worker image. It permits no database, process, network, native-image
load or file-write effect. The native supervisor remains the explicit
Linux/CPython 3.12/x86-64 profile; no additional processor or ABI is qualified.
The unchanged complete worker is not repeated for the source relocation.

Five original held-vault commit tests are now selected explicitly in the public
suite. Their class AST is exact; their table binding and inherited methods are
verified, with only the existing public workspace setup differing from the
retained harness. The new complete run passes **866 distinct tests**, retaining
all 861 prior test identities and their relative order. No failures or skips
occur. All **244 inputs** remain stable. Among the prior 161 inputs, only the
receipt runner changes, adding coverage for qualification Python, C and native
binary files; the other 160 remain unchanged.

Dedicated worker/process/crash tests retain their original bounded harnesses.
The library installation is not a public qualification service or a physical
provider. [Next work](artifacts/implementation/runtime-qualification-package/NEXT.md)
integrates real service ownership and reproducible configuration with an
enforceable storage/recovery profile, then typed PAT tools. Prompt synthesis and
learning, persistent MCU programs, physical I/O/driver/hub providers, native
Harness installation, microscope commissioning and the remaining research and
home/laboratory/manufacturing scenarios stay in scope. The goal remains active.

## Earlier continuation: complete statement-cache integration''')

replace('scripts/check_project_links.py',
    "        *ROOT.glob('artifacts/implementation/pat-statement-cache/*.md'),",
    "        *ROOT.glob('artifacts/implementation/runtime-qualification-package/*.md'),\n"
    "        *ROOT.glob('artifacts/implementation/pat-statement-cache/*.md'),")
replace('docs/qualification-libraries.md',
    'test discovery. The full public regression result is pending.',
    '''test discovery. The full public regression passes **866 tests** with no failures
or skips: all 861 previous tests plus those five checks. All 244 captured inputs
remain stable, including every installed package file. [Verification](../artifacts/implementation/runtime-qualification-package/RUNTIME_RESULTS.json).''')
replace('artifacts/implementation/runtime-qualification-package/README.md',
    'The full 866-test regression is pending.',
    '''The full regression passes **866 distinct tests** with no failures or skips,
preserving all 861 prior identities and their relative order. Every one of the
244 inputs remains stable. [Runtime audit](RUNTIME_RESULTS.json) verifies input
snapshots, output hashes, exact added test identities and installed source.''')
replace('artifacts/implementation/runtime-qualification-package/NEXT.md',
    '''Finish and audit the full public regression: 861 existing tests plus five exact
held-vault commit checks, with all 244 inputs stable. The installed package must
retain the qualified candidate's complete implementation identities. Do not
rerun the unchanged thirty-case worker as a substitute for checking relocation,
input coverage and public-runtime regressions.''',
    '''The full public regression passes: 861 existing tests plus five exact
held-vault commit checks, with all 244 inputs stable. The installed package
retains the qualified candidate's complete implementation identities. Preserve
this receipt and source closure. The unchanged thirty-case worker was not
repeated; relocation, input coverage and public regressions are verified.''')
with (BASE / 'documentation.patch').open('x') as out: out.write(''.join(patch))
print(json.dumps(dict(updated=True, publicTests=866, goalStatus='active')))
