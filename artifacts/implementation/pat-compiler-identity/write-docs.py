"""Reconcile actual identity83 evidence without changing sealed old stages."""
from pathlib import Path
import json

ROOT=Path.cwd().resolve(); B=ROOT/'artifacts/implementation/pat-compiler-identity'
p=json.loads((B/'results/attempt01-passed83/proof.json').read_bytes())
assert p['status']=='passed' and p['counts']==dict(testsRun=83,failures=0,errors=0,
    skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert p['sourceFilesVerified']==214 and p['externalPinsVerified']==159
assert p['actualOrigins']['allOriginsMatched'] and p['testSeconds']==6.04
(B/'results/README.md').write_text('''# Selected compiler identity correction: 83 checks pass

The [complete acquired attempt](attempt01-passed83/proof.json) passes all **83
selected pure tests in 6.040 seconds**, with 8.495 seconds of launcher elapsed
time. There are no failures, errors, skips or expected failures. The selection
contains 20 existing compiler methods, 14 fixed-unit methods, 31 I/O contract
methods and 18 new identity methods. This is a focused isolated result, not a
new full runtime regression or a qualification result.

The [candidate](../implementation01/README.md) closes the known omission of
`typing_extensions` and `idna`. Its version 0.2 compiler manifest commits to 14
selected project source/schema files and 104 code/resource files across seven
required packages. Missing packages/files, duplicate/escaping selected paths,
nonregular files and bounded-acquisition failures refuse setup. Canonical package
ordering and extensionless schema resource coverage are preserved.

Trusted `verify_compiler_identity()` rechecks the selected source and package
bytes without replacing the imported identity. Simulation worker setup invokes
that check. Both previously omitted package code changes, version changes and
missing files are tested; the worker refuses a changed IDNA fixture. Pure lowering
continues to pass filesystem/clock vetoes. No changed fixture code is imported or
executed. Test fixture substitutions do not modify installed packages.

All 214 project files, 217 frozen preparation entries, six active harness inputs
and 159 separately acquired external pins remain unchanged. All 700 actual-origin
records match, with 210 bytecode reads refused and no prohibited attempts. Compiler
and driver identities remain stable. The complete 248-file attempt and original
empty private scratch directory remain retained; acquisition rehashes both inputs
and actual origins. All SQLite/network/subprocess actions in the child are
forbidden. The original 180-second harness and storage/log bounds are unchanged.

The explicit source closure excludes 7,542 unused historical transcript fixtures;
their original archives remain intact. Of 213 inherited project files, only the
compiler, worker identity call and package-set test assertion change. One new test
module is added. Live HMS and the adjacent Harness are untouched. Review is by the
primary agent; helper agents remain usage-limited.

This is a selected deployment identity, not OS/import-origin attestation or a
general optional-dependency resolver. The harness separately verifies the actual
selected origins. Current I/O group setup must use this new identity and bind the
complete worker/configuration/case association. Aggregate quotas, persistent
qualification service, public PAT tools, learning and physical device/driver/hub
controls remain unfinished. Historical successful trials do not qualify this new
candidate. See the [design](../DESIGN.md) and
[remaining qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
''')
progress=ROOT/'PROGRESS.md'; s=progress.read_text()
s=s.replace("five-package identity; the latter still excludes imported optional dependencies.",
    "five-package identity; that historical stage excludes imported optional dependencies.\nThe later isolated identity83 correction below closes those two known omissions.")
marker='The separate [qualification supervisor rebase]'; assert s.count(marker)==1
addition='''The [selected compiler identity correction](artifacts/implementation/pat-compiler-identity/results/README.md)
passes **83 pure tests in 6.040 seconds**: 20 existing compiler methods, 14
fixed-unit methods, 31 I/O contract methods and 18 new identity checks. The version
0.2 manifest and digest domain now include both known omitted dependencies,
`typing_extensions` and `idna`, alongside the original five packages. Trusted
setup rechecks the selected source/package bytes and refuses changes without
refreshing the imported identity. Simulation worker setup invokes this check;
pure compilation stays free of identity acquisition and clock reads.

The tests cover actual dependency-file substitutions, versions, missing files and
packages, canonical inventory ordering, unsafe/duplicate paths, nonregular files,
bounded reads, acquisition ceilings, detached results and worker refusal. All 214
project files, 217 frozen entries, six harness inputs and 159 external pins remain
stable. All 700 origin records match; 210 bytecode reads are refused and no
prohibited attempts occur. The complete 248-file attempt and original empty
scratch root are acquired. No failure, rule relaxation or limit widening occurred.
Three inherited files change and one test module is added; 7,542 unused historical
fixture files are explicitly excluded while their original archives stay intact.
Live HMS and the adjacent Harness remain unchanged; review is by the primary agent.

This closes the documented gap for the supported seven-package setup. Complete
current I/O worker/configuration attestation, exact group execution, actual
aggregate quotas and public qualification remain unfinished. It is not OS or
general import-origin attestation; historical fixtures do not qualify the changed
candidate. Persistent Arduino applications, agent learning and physical driver
and intelligence-hub controls remain part of the active goal.

'''
s=s.replace(marker,addition+marker); progress.write_text(s)
page=ROOT/'docs/prompt-to-pat.md'; s=page.read_text()
marker='An operator says, for example,'; assert s.count(marker)==1
s=s.replace(marker,'''The [compiler identity correction](../artifacts/implementation/pat-compiler-identity/results/README.md)
passes 83 pure checks. It includes both previously omitted validation dependencies
and detects selected source/package changes during trusted worker setup, while
keeping pure lowering free of filesystem reads. The supported seven-package
identity does not itself attest the deployment or qualify a current I/O group.
Exact group execution, aggregate quotas and automatic promotion remain unfinished.

'''+marker); page.write_text(s)
page=ROOT/'docs/io-driver-hub-control.md'; s=page.read_text()
s+='''
The [compiler identity correction](../artifacts/implementation/pat-compiler-identity/results/README.md)
passes 83 pure checks and closes the known two-dependency omission. Trusted worker
setup can now refuse changes to the selected seven-package compiler closure.
This is a prerequisite for reusable PAT evidence, not proof of current physical
driver, hub, operating-system or complete I/O qualification identity. Exact group
execution and aggregate enforcement remain required.
'''; page.write_text(s)
page=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'; s=page.read_text()
old='| Current implementation and configuration identity | Harness pins actual selected imports; compiler identity still has its documented optional-dependency gap | Reconstruct the current worker/environment, close identity scope and bind artifact/config/policy/source/attempt/run associations. Historical fixture identities remain historical |'
new='| Current implementation and configuration identity | Harness pins actual selected imports; the [identity83 correction](../pat-compiler-identity/results/README.md) includes the two known omitted packages, versions the compiler identity and adds trusted setup rechecks | Bind the complete current I/O worker/environment, selected import closure and artifact/config/policy/source/attempt/run associations. The seven-package compiler profile is not full deployment attestation. Historical fixture identities remain historical |'
assert old in s; s=s.replace(old,new)
s=s.replace('group execution, closes the current identity scope and enforces aggregate budgets',
    'group execution, uses the new selected compiler identity within complete trusted\nsetup attestation, and enforces aggregate budgets')
page.write_text(s)
page=ROOT/'scripts/check_project_links.py'; s=page.read_text()
marker="        ROOT/'artifacts/implementation/pat-io-lifecycle-semantics/DESIGN.md',"
assert s.count(marker)==1
paths=['DESIGN.md','implementation01/README.md','harness01/README.md','harness01/SCOPE.md','results/README.md']
s=s.replace(marker, '\n'.join("        ROOT/'artifacts/implementation/pat-compiler-identity/"+p+"'," for p in paths)+'\n'+marker)
page.write_text(s)
print(json.dumps(dict(tests=83,sourceInputs=214,externalPins=159,proseReconciled=True)))
