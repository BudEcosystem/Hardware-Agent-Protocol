# Complete original vault import with guarded canonicalization

**The original complete 30-case worker/import/cold-vault-history scope passes.**
The worker finishes within its unchanged 60-second bound, and the full parent
finishes in 127.614 seconds within its original 180-second bound. One qualification
worker produces thirty manifests; the actual semantic reducer inspects every case,
then one import intent, one immutable vault manifest and one authority publication
are committed. Warm replay and cold-vault replay after a configuration change
return the original result without a replacement worker, replan or semantic replay.

The isolated candidate changes one production module, `hms/contracts.py`, plus
the original test's expected consumer identity. It preserves validation, parser
rules, floating-point encoding, error wrapping and output limits. Integer-only
serialization uses freshly ordered containers and guarded standard-library JSON.
The [pure evaluation](../../verification/pat-integer-canonical-evaluation/README.md)
passes **1,668 differential cases** and measures about **27.5% lower median CPU**
time across nine fixed pairs. All **nine inherited public contract tests** also
pass on normal imports of the frozen implementation, including retained intent
digest fixtures. The public runtime remains unchanged.

The [read-only audit](audit_actual.py) holds **57 original owner/writer locks** and
verifies **4,259 retained files / 35,391,693 bytes**, 265 producer-image files,
independently derived consumer identities and four unchanged source databases.
It opens no worker case databases. Every one of the **2,798 vault bodies** and
**4,011 references** is checked, and all original bundle, control and output bytes
match their imported copies. Manifest, intent, publication, evaluation, inspection
and output-closure digests are independently recomputed or checked against their
exact bodies. The audit does not rerun the semantic reducer; its execution and
complete case inspection belong to the original passing scope.

The original process/descriptor association is verified. Launch/reap elapsed
bounds are 57.776081208–57.776777580 seconds; supervisor and waited-worker CPU
use are 8.727559 and 32.439116 seconds. The unchanged sealed native scanner records
one root and 2,426 attempt scans. These are observations of this trial, not matched
whole-worker speedup evidence or deployment timing guarantees. Global pressure
does not establish a waiting cause, and observer overhead remains included.

Authority storage is 690,176 bytes; the vault is 15,448,064 bytes under its original
15 MiB cap, leaving 280,576 bytes of unreserved headroom. The source authority has
zero application operations/claims and zero board effects. Imported synthetic
evaluation reports zero unresolved effects. This is simulation evidence; physical
outcomes, backed capacity and aggregate disk quota remain unqualified.

[Results](RESULTS.json), [original receipt](harness01/attempts/attempt01-actual/result.json),
[contract tests](contract-controls.json), [design](DESIGN.md),
[source review](implementation01/source-review.json), [scope](harness01/SCOPE.md),
[next work](NEXT.md). All earlier failed trials remain unchanged. Review is by the
primary agent only. Raw state is retained at `/tmp/hms-integer-canonical-actual-egxi2s7w`
and acquired here; future temporary-path availability is not guaranteed.

The authority-vault catalog profile, business-commit evidence boundary, public
qualification/PAT mounting and backed control capacity remain unfinished. So do
the natural-language learning loop, persistent Arduino applications and actual
device I/O, driver, hub and microscope providers. The full HMS goal remains active.
