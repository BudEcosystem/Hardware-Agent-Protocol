# Bud Hardware Model Standard

An independent research and design project for agents operating physical devices, from tiny microcontrollers and microscope retrofits to instrument fleets and industrial cells. Intended agent host: the adjacent `Bud-Meta-Harness` repository. This project is **not an implementation of Anthropic's unpublished MHS specification**.

**Current status:** the executable local simulation runtime combines the registry, admission policy, durable journal, checked API/SDK and `hctl` CLI. A native Harness overlay exercises real tool/PTC calls at a pinned commit in an isolated checkout, with full artifact and aggregate builds passing. A local MCP projection supports current and legacy clients over stdio. The runtime can mount multiple local and compact C simulation routes under one authority, with immutable operation routing, durable mappings, receipt reconciliation and host-process recovery. An explicitly selected shared-board GPIO/PWM simulation also uses the same public tools and resource admission. Primary-source research and checked WoT descriptions support the design. Real adapters, complete commissioned firmware, production Harness integration and physical validation remain unfinished. The user goal remains active. [Progress and requirement audit](PROGRESS.md) records the evidence and remaining work.

The [PAT foundation is now integrated into the main runtime](artifacts/implementation/runtime-pat-foundation/README.md).
All **861 tests pass**, preserving the original 748 tests and adding 113 checks.
Eight production modules are exact copies of the verified candidate, covering
commit-time validation, compiler identity, static resource validation and compact
simulation storage. Public qualification, prompt learning and physical I/O,
driver and intelligence-hub providers remain unfinished.

The [prepared-statement comparison](artifacts/verification/pat-statement-cache-evaluation/README.md)
passes 62 checks across the complete capture query set, exact baseline pages and
warmed authorization guards. A 256-entry authority cache has 38.46% lower median
local capture CPU across nine fixed pairs. This supports a separate worker
integration candidate; the public runtime and full-worker qualification status
are unchanged. The [binding review](research/host-contract/sqlite-cache-binding/README.md)
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
remains unfinished. The main runtime's 861-test source is unchanged.

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
