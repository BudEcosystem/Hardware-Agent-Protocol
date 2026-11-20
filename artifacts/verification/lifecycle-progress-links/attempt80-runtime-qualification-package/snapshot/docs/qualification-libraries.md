# Installed qualification libraries

The main project now contains the verified finite-I/O qualification libraries:
40 additional `hms` modules and the 42-file `hms_qualification` package. All files
match the successful [worker-to-PAT candidate](../artifacts/implementation/pat-statement-cache/README.md)
byte-for-byte. The existing 43 host modules and seven schema files are unchanged.
The [installation record](../artifacts/implementation/runtime-qualification-package/README.md)
distinguishes this source integration from public service mounting.

| Component | Responsibility |
|---|---|
| `hms.pat_io_*` | Bound input capsules, finite matrices, simulated I/O trials, capture and independent history checks |
| `hms_qualification.supervisor` | Retain the original attempt and owned worker association, validate the fixed image, enforce the declared worker limits and retain terminal outputs |
| `hms_qualification.evidence` | Read original archives and reduce their recorded finite-I/O evidence |
| `hms_qualification.evidence_vault` | Retain exact immutable bodies/manifests and provide owner-held evidence views |
| `hms_qualification.evidence_authority` | Record original import intent and publish authority-owned references to the retained evidence |
| `hms_qualification.vault_recorded_io` | Bind that publication to catalog promotion, complete candidate selection and deterministic PAT admission |

The earlier compact and recorded-I/O packages retain their separate versioned
profiles. Their presence does not migrate an existing store, make profiles
interchangeable or grant a caller permission to choose one dynamically.

Import inspection verifies 39 package module origins, 17 unusable legacy names,
four initializer-drift refusals and a 267-file producer image. Installed compiler,
driver, worker, supervisor, consumer, vault and host identities exactly match the
qualified candidate. Inspection performs no database, process, network, native
image load or file-write operation. This identity equality preserves code
provenance; qualification still binds to the actual installation, configuration,
calibration, permissions and endpoint sessions. It does not transfer qualification
between deployments or settle earlier unknown effects.

The native supervisor profile is explicitly
`hms.retention.linux-cpython312-x86_64/1`. Its binary and C source are installed
together and are included in public runtime receipt snapshots. The loader keeps
the original binary hash, platform/ABI checks and sealed memory image. Other
processors, Python ABIs and GB10-class deployments need their own implemented
and qualified host profile. There is no automatic compilation or weaker scan
fallback hidden behind this profile.

The public Runtime, CLI and MCP method set is unchanged. These are installed
libraries for trusted integration; importing a package does not start a
qualification service, worker or learning agent. Public qualification remains
unavailable until its storage provider supplies caps before mutation/recovery,
hard aggregate enforcement across all writers and sidefiles, backed capacity
for owed control continuations, and control-only recovery when bulk is full or
unavailable. [Control-storage requirements](control-storage.md).

The five existing held-vault commit checks are now selected explicitly by the
public suite. They cover valid held evidence and refusal after expiry, release,
replacement or owner mismatch. Their method bodies are unchanged; inherited
Journal checks continue to run in their original public suite. Dedicated worker
and crash suites retain their bounded harnesses and are not added to default
test discovery. The full public regression passes **866 tests** with no failures
or skips: all 861 previous tests plus those five checks. All 244 captured inputs
remain stable, including every installed package file. [Verification](../artifacts/implementation/runtime-qualification-package/RUNTIME_RESULTS.json).

For the user's prompt-to-PAT system, these libraries supply qualification and
deterministic reuse mechanisms. Natural-language synthesis, experience-driven
candidate proposals, service ownership and persistent endpoint installation
remain implementation work. Device I/O, driver lifecycle and hub resources must
all participate in current applicability and ownership checks; installed host
libraries do not physically qualify their providers.
