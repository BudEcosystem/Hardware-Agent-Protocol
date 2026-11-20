# Standing PAT and original native qualification source review

Status: **source only, not imported, compiled, tested, or executed**. This task
adds only `project/hms/standing_pat.py` and this note. It does not create an
attempt receipt, install a passed catalog entry, launch the native controller,
or manufacture evidence. Root source review still gates every execution.

## Narrow qualified domain

The module accepts `hms.pat.standing-controller/0.1` for one literal synthetic
kernel configuration: lower20000, upper30000, required improvement0, on-feedback
minimum500, sample10, demand/feedback max age100, both dwells0, feedback window50,
output/loss policy0/1/0/0. Parameters must be `{}`. Activation cap100,
commanded-on maximum500 and lease horizon1000 are exact, not upper-domain claims.
The fixture is mask3, epochs1/1, boot1, incarnation a0..af, firmware b0..cf and
manifest c0..df. Its only evidence mode is simulation. Physical eligibility and
protected control capacity remain false.

The original native controls' twelve named case functions are pinned in order,
with all twelve exact C/header source hashes hardcoded. A pass of these controls
is used only for this literal domain and the negative/fault coverage actually
contained in those exact sources. It does not qualify arbitrary parameters,
units, devices, source bindings, drivers, lease horizons, installations, target
fit, physical outputs, scheduling bounds, or aggregate storage capacity. Host
lifecycle and crash controls remain separate required validation.

Artifacts and compilations separately pin the full immutable installation,
configuration bytes, source/domain identity, driver image/source, qualification
binary image and host implementation. Catalog receipt existence cannot supply a
resource claim or authorize an endpoint request.

## Public installed-service interface

`installed_artifact(installation)` produces the fixed candidate document, with
`taskKind='standing-cooling-control'` and
`inputProfile='synthetic-demand-rpm-v1'`. Artifact `id/taskKind/inputProfile` may
be other valid labels, but every remaining field must exactly equal the literal
installed domain. A label change cannot change configuration or qualification.
The `parameters` object is always empty.

`parse_artifact(value, installation)` and `compile_artifact(value, installation)`
validate that domain. `Compiled.document` is a detached JSON-safe mapping;
`Compiled.configuration` is the existing `standing_wire.Configuration` object.
`installation_digest` is exactly
`identity('HMS-STANDING-INSTALLATION-v0.1', installation)`.

Trusted setup constructs:

```
producer = InstalledNativeProducer(journal, fixed_evidence_root, manifest=manifest)
catalog = StandingCatalog(journal, policy, producer, create=True)
```

`create=False` requires the existing opt-in catalog and exact installed producer
identity; it does not create/migrate tables. Producer paths and pinned digests are
trusted setup arguments. None appears in application deployment requests.

Management methods are `publish(context, artifact) -> artifactDigest`,
`record_evaluation(context, artifactDigest, evaluatorId, runId) -> evaluationDigest`,
`promote(context, artifactDigest) -> decisionDigest`, and `suspend(context,
artifactDigest)`. They authenticate admin authority and use the same Journal.
`record_evaluation` accepts only installed original names; it has no results,
passed flags, caller evidence, command, module or path argument. Exact replay is
idempotent; an evaluator/run cannot be reassociated to another artifact.
Publishing alone leaves the artifact a candidate. Promotion reopens and checks
the original receipt and all current pinned bytes.

Admission uses the parent's scope order:

```
with policy.hold_image():
    with catalog.hold_selection(context, request):
        with journal._transaction():
            selected = catalog.select(context, request)
            # Commit host admission using selected.document/configuration.
```

`Selected.document` includes the full immutable artifact, compilation,
evaluation, promotion and their digests plus installation and catalog revision.
It is a detached JSON-safe document. `Selected.configuration` is a typed wire
Configuration. Digest properties are also exposed. `select` registers its pure
final commit revalidation. `check_selection(selected, context)` repeats that
check/registration for the store. It requires the original held context and
transaction. Inventory changes, missing/multiple compatible promoted entries,
changed installation/evidence, expiry or withdrawal refuse fresh selection.
Historical replay belongs to the store and must precede fresh catalog access.

Tables `sp_meta`, `sp_artifacts`, `sp_evaluations`, and `sp_decisions` share the
standing Journal authority database. Each retained collection is bounded at16;
there is no eviction or history deletion. The catalog is pinned to one installed
original evaluator/run bundle. This initial profile deliberately does not expose
a broad learned synthesis or qualification service.

## Exact future runner evidence format

The reviewed future runner must produce these files from its **actual single
original native `standing_controls` process**. This module never writes them.
JSON files are exact canonical bytes (`canonical(document)`, no trailing
newline); stdout is retained exactly including its final newline. Hashes use
`sha256:` plus64 lowercase hex. The fixed evaluator ID is
`standing-native-controls-v1`; run and attempt IDs are valid HMS identifiers.

The producer manifest has exactly these keys:

```
profile: "hms.standing-native-producer/0.1"
evaluatorId: "standing-native-controls-v1"
runId: <original installed run ID>
runnerDigest: <digest of original reviewed runner image/source identity>
domainDigest: standing_pat.DOMAIN_DIGEST
sourcePins: standing_pat.SOURCE_PINS
binaryPath: <fixed relative path below fixed_evidence_root>
binaryDigest: <hash of original native qualification executable>
argv: [<absolute fixed_evidence_root/binaryPath>]
reservationPath: <fixed relative original reservation JSON path>
reservationDigest: <hash of exact reservation bytes>
receiptPath: <fixed relative original attempt JSON path>
receiptDigest: <hash of exact attempt bytes>
stdoutPath: <fixed relative original stdout path>
stdoutDigest: <hash of exact original stdout bytes>
stderrPath: <fixed relative original stderr path>
stderrDigest: <hash of exact original stderr bytes>
```

All five paths must be distinct regular files. Absolute paths, traversal and
symlinks in the retained paths are refused. `sourcePins` is exactly the twelve
hardcoded originals; those files are read from the copied project's installed
`ROOT`, not from caller-selected paths. `binaryDigest` must also equal the
installation's `qualificationImageDigest`. The original single-element argv is
exactly the fixed binary path, with no application arguments.

The original **reservation**, persisted before launch by the runner, has exactly:

```
profile: "hms.standing-native-reservation/0.1"
evaluatorId, runId, attemptId, runnerDigest, domainDigest,
sourcePins, binaryPath, binaryDigest, argv: <same exact original association>
limits: {cpuSeconds:10, wallSeconds:30, fileBytes:1048576, processes:1}
state: "reserved"
```

The original **attempt receipt**, persisted only after the original process was
waited and all owned child handles were closed, has exactly:

```
profile: "hms.standing-native-attempt/0.1"
evaluatorId, runId, attemptId, runnerDigest, domainDigest,
sourcePins, binaryPath, binaryDigest, argv: <same original association>
reservationDigest: <hash of original reservation>
stdoutDigest, stderrDigest: <hashes of retained original streams>
exitCode: 0
terminationSignal: 0
startedMonotonicNs: <canonical decimal u64 string>
finishedMonotonicNs: <canonical decimal u64 string>
ownership: {
    pid: <positive original child pid>,
    waitedPid: <the same pid actually waited by its living owner>,
    spawnCount: 1,
    reaped: true,
    cleanupComplete: true,
    openChildHandles: 0
}
physicalQualification: false
protectedCapacity: false
```

Start must precede finish and elapsed time must fit30 seconds. Integer fields
reject booleans/floats. A PID is retained association only: the loader never uses
it to signal or recover process authority. Required original stdout is exactly:

```
{"cases":12,"assertions":638,"physical_qualification":false}
```

It includes one trailing newline; stderr must be empty. Exit, source, binary,
argv, reservation linkage, original run/attempt linkage, timestamps, cleanup,
result bytes and every manifest pin are all checked. The loader derives the
catalog outcome from these original bytes; callers cannot supply an outcome.
Twelve cases/638 assertions alone never qualifies another artifact domain.
The runner must implement the stated process/resource limits and truthful
commit-before-launch/wait-before-receipt ordering; matching JSON labels alone
are not independent proof that those actions occurred.

## Held evidence and limits

A producer snapshot occurs outside the Journal transaction. It opens and locks
all seventeen original source/binary/reservation/receipt/stream files for shared
reading, validates current exact bytes, and retains the bytes and open handles
through the catalog/admission commit. The snapshot maximum is8MiB; binary2MiB,
each source1MiB, each receipt/reservation16KiB, each stream4KiB. Its pure commit
check uses held identity, thread, active/enabled state and a two-second lease;
it performs no filesystem/provider I/O or worker launch. Full inventory is read
before the snapshot and checked again inside selection and before commit.

This is a trusted local POSIX publication contract. The installed reviewed
runner must publish originals once and honor shared locks against modification;
it is not a cryptographic attestation or a sandbox against arbitrary same-user
file writers. The catalog does not independently prove a claimed process ran
from JSON; trust rests on the installed original runner and pinned retained
attempt stream. No manual evaluation or pass-receipt constructor is exposed.

## Remaining gates

Root must review this source and the actual runner implementation before imports,
builds or execution. No receipt currently exists from this task. Later authorized
checks must establish exact domain rejection, original native12/638 output,
source/binary/result/argv/cleanup refusal, missing evidence, held-lease expiry,
reassociation conflict, promotion/selection and complete inventory guards, and
unchanged finite/PAT profile rejection. The native generic pass remains only one
piece of source-scoped synthetic qualification; physical, capacity, deployed
hardware and broader learned-domain claims remain unsupported.
