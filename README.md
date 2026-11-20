# Bud Hardware Model Standard

An independent research and design project for agents operating physical devices, from tiny microcontrollers and microscope retrofits to instrument fleets and industrial cells. Intended agent host: the adjacent `Bud-Meta-Harness` repository. This project is **not an implementation of Anthropic's unpublished MHS specification**.

## BHMS: the protocol, SDKs and tools

BHMS (Bud HMS, protocol version `2026-11-15`, with `2026-11-13` compatibility) is the protocol this research produced: JSON-RPC 2.0 in the shape of MCP,
for AI agents, programs and people that discover, observe and operate physical devices, with durable idempotent
operations, honest evidence labels, leases with fencing, unknown outcomes that are never guessed, and a stop that never
waits. It is tested against simulated devices and host-built firmware; no physical device has been validated yet.

- **Start here:** [developer documentation](docs/bhms/index.md), [quickstart](docs/bhms/quickstart.md) (a device server,
  Claude through MCP, an OpenAI model, a gateway; every step executed by the test suite), [concepts](docs/bhms/concepts.md).
- **Specification:** [`spec/bhms`](spec/bhms/README.md) (chapters 01 to 15, JSON Schema, examples, conformance index).
- **Code:** Python SDK, gateway, agent bridges and conformance runner in [`sdk/python`](sdk/python/pyproject.toml)
  (`pip install -e 'sdk/python[mcp,openai]'`, then `bhms --help`); [`sdk/typescript`](sdk/typescript/README.md);
  the C library and Arduino wrapper for microcontrollers in [`sdk/c`](sdk/c/README.md); SimLab, a simulated laboratory
  with real-protocol instruments, in [`simlab`](simlab/README.md); the open BHMS Arm in [`hardware/actuator`](hardware/actuator/README.md).
- **Changes and numbers:** [migration notes](docs/bhms/migration.md), [performance](docs/bhms/performance.md),
  [final validation report](docs/bhms/validation-report.md).

The rest of this README describes the earlier HMS research runtime (`hms/`, `protocol/`, `tests/`) and its retained
evidence.

**Current status:** the executable local simulation runtime combines the registry, admission policy, durable journal, checked API/SDK and `hctl` CLI. A native Harness overlay exercises real tool/PTC calls at a pinned commit in an isolated checkout, with full artifact and aggregate builds passing. A local MCP projection supports current and legacy clients over stdio. The runtime can mount multiple local and compact C simulation routes under one authority, with immutable operation routing, durable mappings, receipt reconciliation and host-process recovery. An explicitly selected shared-board GPIO/PWM simulation also uses the same public tools and resource admission. Primary-source research and checked WoT descriptions support the design. Real adapters, complete commissioned firmware, production Harness integration and physical validation remain unfinished. [Progress and requirement audit](PROGRESS.md) records the evidence and remaining work.

The [qualification libraries are installed in the main project](artifacts/implementation/runtime-qualification-package/README.md):
40 additional host modules and 42 package files retain the exact qualified source.
The installed identity inspection matches the successful candidate, including its
267-file worker image. A new full public run passes **866 tests**, preserving all
861 prior tests and adding five original vault commit checks, with **244 stable
inputs** including native C and binary files. [Library guide](docs/qualification-libraries.md).
Public qualification/PAT service mounting, prompt learning and physical providers
remain unfinished; the native supervisor retains its explicit host/ABI profile.

An isolated [intent handoff](artifacts/implementation/prompt-intent-handoff/README.md)
now retains natural-language intent revisions and checked agent proposals, with
22 focused tests passing. It preserves exact replay and refuses stale proposals;
it does not qualify, promote or execute them. The [source audit](artifacts/design/prompt-intent-handoff/README.md)
records the remaining learning/qualification and Harness integration gaps.

The [selection-reuse host candidate](artifacts/implementation/standing-host-selection-reuse/RESULTS.md)
passes 34 compiler comparisons and nine native management/freshness cases.
Private compilation reuses one freshly validated snapshot within the call,
reducing installation validations from five to one while preserving current
authority and final guards. Its [subsequent full-capacity attempt](artifacts/implementation/standing-host-selection-capacity/RESULTS.md)
still hits the thirty-second limit, retaining 110 settled and one prepared START.
Full capacity and performance benefit remain open.
The [phase-kernel firmware](artifacts/implementation/standing-endpoint-phase-kernels/RESULTS.md)
passes six complete differential traces and saves another 716 flash bytes.
Its failed link charges 39,186 flash bytes, exceeding the original AVR application
allowance by 6,930 bytes; no valid target image or complete stack proof exists.

The isolated [Arduino runtime integration](artifacts/implementation/avr-link-integration/README.md)
joins the finite endpoint, serial receive/transmit, Timer1 and durable boot
reservation. Eleven integrated register-model cases pass normally and under
ASan/UBSan, alongside the original endpoint suite. The combined ATmega328P image
cross-links at 21,778 flash bytes and 1,343 static SRAM bytes. These are model
and build results; target execution, physical I/O and persistent applications
remain unfinished.

The isolated [compact-bitmap storage candidate](artifacts/implementation/compact-bitmap-store/README.md)
passes 329 focused checks and a paired 426-operation screen while preserving
current identity checks and full durability barriers. Its full 4,270-file writer
still times out at the original 180-second limit. A read-only audit verifies
35 retained images, including 1,814 complete files and all 169 directories in
the interrupted writer. The candidate remains unadopted; all 244 public inputs
retain the existing 866-test baseline. The preceding
[attribution](artifacts/verification/full-storage-attribution/README.md) and new
[existing-state overwrite review](artifacts/verification/state-overwrite-hypothesis/README.md)
retain the evidence and next hypothesis. An [existing-state replacement draft](artifacts/implementation/existing-state-replacement/STATUS.md)
has source only; its delegated preparation was stopped by automatic review and
no model or replay was executed.

Device I/O, drivers and the intelligence hub share one
[managed resource graph](docs/io-driver-hub-control.md) and an explicit
[I/O and driver boundary](spec/12-io-driver-boundary.md). New acquisition,
configuration and native queue handoff retain their actual effects and authority.
The isolated
[hub recovery increment](artifacts/implementation/owned-hub-recovery/RESULTS-REVIEW.md)
passes five groups covering interrupted terminal writes, retained handles,
typed computation, replay and limits. A separate [owner-death harness](artifacts/implementation/owned-hub-crash-harness/README.md)
passes twelve actual process-death checkpoints, preserving six not_started,
three unknown and three completed outcomes without relaunching historical work.
The [writer-deferral controls](artifacts/implementation/owned-hub-writer-deferral/RESULTS-REVIEW.md)
add three deliberate held-writer cases after leader exit and owner death. Recovery
retains admission until the writer settles, then records unknown; independent
auditing verifies the retained rows, leases and all ten controlled process reaps.
It is not yet a public mount or a qualified GB10/GPU/driver/device provider.

The [standing endpoint design](artifacts/design/standing-endpoint-programs/README.md)
specifies local triggers, feedback, renewable authority, retained evidence and
shared I/O ownership for a narrow Arduino controller. The [fit candidate](artifacts/implementation/standing-endpoint-fit/RESULTS-REVIEW.md)
passes thirteen native cases / 673 assertions in both normal and sanitizer builds,
plus the finite endpoint and runtime regressions. It reduces flash load by 582
bytes and meets the 160-byte static-growth allowance. Its ATmega328P link still
fails: 43,064 flash-load bytes exceed physical flash by 10,296 bytes.
Target fit, complete learning, installation and physical qualification remain
unfinished. The [prompt-to-PAT contract](docs/prompt-to-pat.md) keeps planning,
perception and evidence failures distinct.

The subsequent [LTO profile](artifacts/implementation/standing-endpoint-lto/RESULTS-REVIEW.md)
compiles all twelve units but still fails linking: **41,892 flash-load bytes**,
or **9,124 bytes over physical flash**. Static SRAM remains 1,503 bytes. The
1,172-byte reduction includes a stronger explicit symbol-retention policy.
Both attempts and 32 command reaps are audited; no valid ELF or final combined
stack/timing proof exists. The unchanged native source retains its parent tests.

The [copy/boundary successor](artifacts/implementation/standing-endpoint-copy-boundary/RESULTS-REVIEW.md)
passes fourteen standing cases / 766 assertions in normal and sanitizer builds,
plus the finite/runtime regressions. Flash load is now 41,810 bytes, still 9,042
over physical flash. Its generated standing branch retains six caller bytes
instead of 101; complete stack/ISR analysis and target fit remain open.
The subsequent [shared-kernel refactor](artifacts/implementation/standing-endpoint-shared-kernel/RESULTS.md)
implements shared time/serialization work across both protocols. Four complete
baseline/candidate traces match, including 475 new boundary assertions; numeric
controls pass 13,014 assertions in each mode. Flash load falls by 1,908 bytes to
39,902, still 7,134 above physical flash. All 50 command reaps are audited.
There is no valid target ELF or complete stack/timing qualification.

The [host deployment integration plan](artifacts/design/standing-host-deployment/HOST-DEPLOYMENT-PLAN.md)
maps the remaining journal, shared ownership, version-2 transport, durable
commit-before-ACK collection and standing PAT work to existing source. Its isolated
implementation now passes [twenty native host cases / 173 checks](artifacts/implementation/standing-host-deployment/RESULTS-REVIEW.md).
It includes one shared finite/standing authority, an original-evaluator-backed
literal PAT path and a 16 MiB all-writer logical partition. Prepared-only recovery,
durable reply disputes, policy replacement and separate REVOKE uncertainty have
controls. A separate [thirteen-cut owner-death increment](artifacts/implementation/standing-host-owner-death/RESULTS-REVIEW.md)
now passes with the native endpoint surviving each killed host. Historical
possible effects are not resent, and exact terminal evidence gates claim release.
The [boundary successor](artifacts/implementation/standing-host-boundaries/RESULTS.md)
adds eight authority/replay and ten synchronous storage-failure controls that
pass. Its mutation-capacity attempt reaches the unchanged 30-second wall limit
after 68 never-handed-off mutations; the failed attempt is retained and the
remaining matrix is unexecuted. Full capacity, broader failure modes, public mounting and physical drivers remain
open; these results are partial validation of the fixed synthetic profile.

The [PAT foundation](artifacts/implementation/runtime-pat-foundation/README.md)
provides commit-time validation, compiler identity and static resource checks.
The new [statement-cache integration](artifacts/implementation/pat-statement-cache/README.md)
passes **nineteen catalog controls and the complete thirty-case worker → vault →
catalog → PAT application flow**. One simulated application completes once, with
original-key replay, configuration drift refusal and cold history intact.

The worker completes in about 57.7 seconds under the original 60-second limit;
the parent completes in 141.1 seconds under 180 seconds. The only production
change is a 256-statement authority Journal cache. That same edit is now in the
public runtime, where the preceding full run passed **861 tests** with 161
stable inputs. The subsequent library installation above extends that coverage.
Public qualification, prompt learning and physical device/driver/hub providers
remain unfinished. One successful local run does not qualify deployment timing.

The preceding [local comparison](artifacts/verification/pat-statement-cache-evaluation/README.md)
passes 62 checks and observes 38.46% lower median capture CPU; this is not a
whole-worker speedup claim. The [binding review](research/host-contract/sqlite-cache-binding/README.md)
adds 4,025 fully read LF lines and records cursor/memory lifetime constraints.

The [current worker diagnostic](artifacts/verification/qualification-current-profile/README.md)
retains a complete-matrix request and the original limits. It stops at the deadline
with 21 case manifests, records current SQLite/validation/durability costs and
publishes no qualification or application. A separate encoder experiment passes
1,875 semantic cases but is not adopted because its timing benefit is inconsistent.
The subsequent [SQL metadata experiment](artifacts/verification/pat-sql-metadata-evaluation/README.md)
matches 410 differential cases but is also unadopted: fewer queries produce about
6.3% higher median CPU in the fixed local comparison. The
[statement-cache review](research/host-contract/sqlite-statement-cache/README.md)
adds 477 fully read LF lines and identifies a separate hypothesis to measure:
164 distinct authority capture statements versus the installed 128-statement
default. This static count does not establish cache misses or a timeout cause.

The [qualification package candidate](artifacts/implementation/qualification-package/README.md)
has explicit package imports and a pinned worker image. Import and identity checks
pass, but its actual thirty-case qualification hit the original worker deadline:
25 case manifests were retained, with no evidence publication or PAT application.
The failure is preserved separately from catalog controls; public integration
remains unfinished. That failed attempt remains retained; the later cache candidate above completes the same matrix.

The earlier isolated [authority-vault catalog](artifacts/implementation/pat-vault-catalog/README.md)
passes 19 controls and the complete thirty-case worker → vault → catalog → PAT
application flow. One simulated GPIO application completes exactly once; original-key
history survives configuration drift and cold vault/bridge reconstruction. Complete
candidate evidence and current device/driver applicability are checked through
admission commit. Public integration, prompt learning and physical device, driver
and intelligence-hub providers remain unfinished.

The preceding isolated [vault batch candidate](artifacts/implementation/pat-vault-batch/README.md)
passes 60 controls for complete bounded evidence views and their admission-commit
checks. Missing batch members refuse the view; expiry rolls back admission, while
post-commit lease failure retains original-key replay. Its distinct catalog mount
is now connected in the isolated profile above; the full learning loop and physical
providers remain unfinished.

The preceding isolated [business commit candidate](artifacts/implementation/pat-business-precommit/README.md)
passes 51 controls for final evidence checks, rollback, clock-floor preservation
and original-key replay after lost commit replies. It adds the transaction boundary
needed by the independent evidence vault; the bounded catalog evidence view,
public integration and physical providers remain unfinished.

Durable ordered procedures coordinate those routes with atomic child admission,
explicit restart continuation and checked CLI/MCP access. The latest full run
passes **861 tests**, with all 161 inputs and compiler identity unchanged.
The previous 748-test result remains an immutable historical baseline.
The earlier 747-test run retains its status-read timeout. A controlled reproduction
and five passing transport tests verify the test-only polling correction within
the original deadline, without mutation retries. Earlier passing and failed runs
remain preserved. The new
[PAT simulation qualification components](docs/pat-simulation-qualification.md)
include closed configuration/domain contracts, shared environment extraction,
an executable isolated fan worker, a catalog evidence gate and a bounded evidence
reducer/store. The corrected store/hook integration passes 46 focused tests with
fresh worker outputs. Later isolated durable supervision and recorded I/O catalog
integration are verified below; the public qualification service remains unfinished.
The pure I/O resource topology library now passes 21 focused tests;
resource admission and the evidence memo are now integrated as libraries, with
corrected compiler dependency identity. Their focused checks pass 32 and 77 tests;
the new full runtime check includes these libraries alongside the topology,
evidence store and evaluation-integrity fixes. A separate synthetic GPIO/PWM
provider is now [mounted through the public tools](docs/io-simulation.md).
Its final four real CLI/MCP transport cases pass after retained failed37 and
failed52 attempts exposed two integration defects and an incorrect resume-test
expectation. Physical providers and executed driver/hub lifecycle control remain
further work.
[Typed PAT compilation and a trusted local promotion catalog](docs/pat-foundation.md)
and [deterministic selection with atomic instances](docs/pat-execution.md)
now extend that foundation as host libraries. A targeted
[compact admission refresh](docs/compact-admission-refresh.md) addresses reproduced
presence expiry without changing the original request bounds; all 25 focused
admission tests pass within that full run. Prompt-driven applications that learn into deterministic
Programs as Tools, and control spanning device I/O, drivers and intelligence-hub
resources, are core requirements with explicit designs; their full implementation
and physical qualification remain open. Historical Harness runs retain their
exact earlier runtime snapshots.

The isolated [recorded I/O catalog integration](artifacts/implementation/pat-io-definition-build/README.md)
passes 21 pure controls and the actual complete 30-case worker/import/catalog/PAT
application/replay scope. Original-key replay adds no effect, configuration drift
refuses fresh reuse, and cold historical replay survives a session change. Earlier
failed scopes remain preserved. Protected control capacity and public mounting
remain unfinished; this is simulated-device evidence.

The [control-storage review](docs/control-storage.md) adds five passing bounded
SQLite experiments and an unchanged-state allocation audit. It specifies separate
evidence/control storage and capacity owed to admitted work. The corresponding
production profile and actual capacity provider remain to be implemented.

An isolated [immutable evidence vault](artifacts/implementation/pat-evidence-vault/README.md)
now preserves the complete retained I/O dataset in a separately capped database.
All 22 distinct methods have passing receipts on identical production code, with
startup and test-assertion failures retained. An [authority-publication candidate](artifacts/implementation/pat-vault-authority/README.md)
now binds that vault to an actual runtime authority and records original import
intents and manifest references. All [25 selected current-production controls](artifacts/verification/pat-vault-authority-controls/README.md)
now pass in separate scopes, with interrupted attempts and the earlier aggregate
failure retained. Actual-run validation through this profile, catalog integration,
public mounting and backed control capacity remain unfinished.
The [fresh actual trial](artifacts/implementation/pat-vault-original-run/README.md)
hit its original worker deadline before import; its partial capture and unknown
worker outcome remain retained for diagnosis.

A [bounded current-worker profile](artifacts/verification/pat-vault-worker-profile/README.md)
now identifies repeated validation/serialization work for evaluation. Its own
original scope also stopped at the unchanged deadline; all retained bytes and
source databases pass the read-only audit. It establishes neither a timeout cause
nor a complete import, and introduces no production change.

A [pure validator evaluation](artifacts/verification/pat-validation-walk-evaluation/README.md)
passes 468 differential cases. Its small, inconsistent timing improvement is
insufficient to adopt it as a deadline correction; production stays unchanged.

The subsequent [one-call topology/proof candidate](artifacts/implementation/pat-io-proof-batch/README.md)
passes 63 pure controls and reduces repeated validation in definition building.
Its full actual trial still reaches the unchanged worker deadline before import;
it remains isolated and does not qualify the end-to-end path. Original results and
verified retained copies are preserved, including the later loss of temporary trees.

A [whole-worker accounting diagnostic](artifacts/verification/pat-worker-accounting/README.md)
now separates parent and child resource use without changing the project or worker
code. Fifteen observer controls pass. The actual scope still reaches the original
deadline with 25 retained case manifests and no import. During its roughly
60-second worker interval, parent and child use 18.45 and 36.58 CPU seconds.
The audit verifies all retained bytes and original launch association; the next
investigation is parent monitoring cost, with no established single timeout cause.

The [retention-scan comparison](artifacts/verification/pat-retention-scan-cost/README.md)
now verifies 72 read-only scans of the original retained tree. A separate
[native host prototype](artifacts/verification/pat-native-retention-prototype/README.md)
passes 20 differential controls and five syscall scopes, with roughly 61% lower
median scan CPU time in fixed local pairs. Original metadata remains unchanged.
The helper is not integrated; full worker/import qualification remains required.

The subsequent [in-process native binding](artifacts/verification/pat-native-retention-binding/README.md)
passes 43 production-build controls, 20 separate instrumented controls and three
actual syscall scopes. It preserves signal exceptions and descriptor cleanup and
adds opened-directory identity checks. It remains isolated, with no new whole-worker
performance or qualification result. Physical I/O, driver and hub providers remain
required parts of the system.

The [isolated supervisor integration](artifacts/implementation/pat-native-supervisor/README.md)
now loads the verified scanner through a sealed memory image. Six loader scopes
and sixteen audit-guard controls pass. The complete actual worker still reaches
its original deadline before import, leaving fifteen manifests and interrupted
effects unknown. All retained state and source identities are verified; no
whole-worker speedup, public adoption or complete PAT qualification is claimed.

The subsequent [native worker accounting diagnostic](artifacts/verification/pat-native-worker-accounting/README.md)
passes 21 pure controls with unchanged project code. Its full trial reaches the
original deadline with twenty-nine manifests and no import. It measures 10.79
supervisor and 35.85 worker CPU seconds, and verifies the original launch and all
retained state without opening interrupted case databases. Qualification remains
failed; exact canonical-serialization evaluation is the next proposed improvement.
Four previously partial API texts are now fully read in a retained overlay.

The latest [guarded canonicalization candidate](artifacts/implementation/pat-integer-canonical/README.md)
passes the **complete original thirty-case worker and authority-vault import**,
including original-key replay and cold-vault history after configuration drift,
within the unchanged limits. It passes 1,668 pure differential cases and nine
public contract tests. The read-only audit verifies every retained vault body and
its original association. This remains an isolated simulation candidate; the
distinct vault catalog profile, public mounting and backed capacity are next.

## Start here

- [Scope and completion requirements](spec/00-scope.md)
- [Architecture and foundational command interface](spec/01-architecture.md)
- [Execution, state, cancellation and recovery semantics](spec/02-execution.md)
- [Registry, tool manager, runtime and performance](spec/03-registry-runtime.md)
- [Home, scientific and manufacturing scenarios](spec/04-scenarios.md)
- [WoT description profile and execution boundary](spec/05-description-profile.md)
- [Workflow, material identity and recovery](spec/06-workflows-materials.md)
- [Constrained endpoint binding](spec/07-constrained-binding.md) and [serial codec](protocol/serial/README.md)
- [Host invocation, identity and durable journal profile](spec/08-host-contract.md)
- [Local registry and simulation runtime](spec/09-local-runtime.md) and [runnable CLI walkthrough](docs/local-control.md)
- [Checked local API contracts and SDK](spec/10-local-api-contracts.md)
- [Experimental compact endpoint wire/state profile](spec/11-endpoint-wire.md) and [implementation/verification](protocol/endpoint/README.md)
- [Device I/O, driver lifecycle and intelligence-hub boundary](spec/12-io-driver-boundary.md)
- [Durable compact host binding and recovery](docs/compact-host-binding.md)
- [Multiple installed simulation adapters](docs/multi-adapter-runtime.md)
- [Shared-board GPIO/PWM simulation and startup](docs/io-simulation.md)
- [Local MCP tools and interoperability evidence](docs/mcp-integration.md)
- [Platform primitives and finite boot reservations](protocol/platform/README.md)
- [Microscope knob retrofit](docs/microscope-retrofit.md)
- [Bud Meta Harness integration](docs/harness-integration.md)
- [Native Harness overlay and frozen 315-test runtime verification](integration/harness/multi-adapter/README.md)
- [Conformance and physical validation plan](docs/conformance-plan.md)

## Research

- [Official MHS source findings and independent implementation critique](research/mhs/notes/findings.md)
- [Protocol landscape](docs/protocol-landscape.md) and [corpus notes](research/protocols/README.md)
- [WoT reuse decision](docs/wot-reuse-decision.md) and [MQTT/Sparkplug binding requirements](docs/transport-guarantees.md)
- [Physical-AI architectures](docs/physical-ai-landscape.md) and [reading notes](research/physical-ai/notes/reading-notes.md)
- [Learned-control deployment profile](docs/learned-control-profile.md) and [GR00T/OpenVLA full review](research/physical-ai/notes/vla-full-review.md)
- [Laboratory corpus](research/laboratory/README.md) and [SiLA/Bluesky/LabOP binding requirements](docs/laboratory-bindings.md)
- [Description/profile review and repairs](docs/profile-review.md)
- [Constrained protocol corpus](research/constrained/README.md) and [embedded implementation evidence](docs/embedded-evidence.md)
- [Planning and skill grounding](docs/planning-and-grounding.md), [planning corpus](research/planning/README.md), and [Modbus/SCPI bindings](docs/instrumentation-bindings.md)
- [Prompt-to-PAT learning and deterministic reuse](docs/prompt-to-pat.md), [bounded procedures](docs/bounded-procedures.md), and [device I/O, driver and hub control](docs/io-driver-hub-control.md)
- [Executable PAT qualification components and their limits](docs/pat-simulation-qualification.md)
- [Host persistence evidence](research/host-contract/README.md) and [AVR target build/UART review](research/constrained/avr/notes/target-build-and-uart-review.md)
- [Home Assistant/ESPHome binding evidence](docs/home-bindings.md), [OSCORE security binding](docs/oscore-binding.md), and [EDHOC full review](docs/edhoc-binding.md)
- [Observe/Blockwise/reliable-CoAP analysis](docs/coap-streaming-binding.md), [feedback and spatial planning](docs/planning-continuation.md), and [local timing measurements](docs/local-performance.md)
- [OPC UA industrial binding review](docs/opcua-binding.md) and [MCP specification corpus](research/mcp/README.md)
- [Current LwM2M Core/Transport review](docs/lwm2m-current-binding.md) and [microscope controller evidence](docs/microscope-controller-binding.md)
- [WoT Architecture full reading and binding analysis](docs/wot-architecture-binding.md)
- [AVR/RP2040 clock, boot and storage evidence](docs/clock-boot-platform.md)
- [Original AVR Timer1 clock implementation and checks](docs/avr-clock-implementation.md), and [full Q-Block review](docs/qblock-binding.md)
- [GB10/DGX Spark hub deployment evidence](docs/gb10-deployment-evidence.md)
- [Search and full-reading backlog](research/PLAN.md)

Raw articles, papers and pinned source checkouts/snapshots are local under `research/`. Acquisition manifests and reading logs are separate: downloaded is not synonymous with read. Source licenses remain with their owners. The small audited JCS library is intentionally [vendored](hms/_vendor/README.md); other research checkouts are reference material. Large model weights, training datasets, recursive submodules and complete Git history have not been acquired.

## Check the draft artifacts

Python 3, `requests`, `beautifulsoup4` and `jsonschema` are used by the local research utilities. The complete Python test suite additionally uses installed MCP SDK 1.26.0 and AnyIO as tester dependencies; the production MCP projection does not depend on that SDK. Native C framing tests additionally require GCC; the stress check uses address/undefined-behavior sanitizers. PDF extraction uses `pdftotext`. These were available in the working environment; reproducible dependency locking is still outstanding.

```sh
python3 scripts/audit_corpus.py
python3 scripts/check_descriptions.py
python3 scripts/check_wot_profile.py
python3 scripts/check_endpoint_scenarios.py
python3 -m unittest discover -s tests -v
python3 scripts/check_serial_native.py
python3 scripts/check_endpoint_native.py
python3 scripts/check_endpoint_integration.py
python3 scripts/check_compact_mcp.py
python3 scripts/check_boot_epoch.py
python3 scripts/check_avr_eeprom.py
python3 scripts/check_host_journal.py
python3 scripts/check_runtime.py
```

The JSON descriptions in `examples/` and `examples/wot/` are synthetic, uncommissioned design examples. WoT TD 1.1 is the chosen host description direction; the action forms now project the full host envelope. Static fixtures pin their original physical-contract files, while executable simulation types use a separately versioned type-bundle digest. Example HTTPS forms are placeholders, not installed endpoints. The CLI uses an authenticated local Unix socket; all processes with one Unix UID share a principal. Checks cover corpus integrity, descriptions, framing, request identity, simulated execution and crash recovery. They do not establish physical behavior, timing or complete protocol conformance. The [AVR build instructions](research/constrained/avr/notes/target-build-and-uart-review.md) reproduce its component-only footprint without flashing hardware.

The [endpoint build](protocol/endpoint/README.md) additionally cross-links the executor, framing and synthetic callbacks for ATmega328P. Its 15,780-byte flash image, 1,335-byte static RAM allocation and conservative static stack analysis fit the declared planning reservations; no target program ran. Qualified clock/NVM/UART and actual device drivers remain separate work. [Evidence consistency audit](artifacts/verification/endpoint-evidence-audit.json) links the retained source, binary and test receipts.
