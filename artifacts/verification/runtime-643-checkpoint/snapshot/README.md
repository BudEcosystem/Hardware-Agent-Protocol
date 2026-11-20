# Bud Hardware Model Standard

An independent research and design project for agents operating physical devices, from tiny microcontrollers and microscope retrofits to instrument fleets and industrial cells. Intended agent host: the adjacent `Bud-Meta-Harness` repository. This project is **not an implementation of Anthropic's unpublished MHS specification**.

**Current status:** the executable local simulation runtime combines the registry, admission policy, durable journal, checked API/SDK and `hctl` CLI. A native Harness overlay exercises real tool/PTC calls at a pinned commit in an isolated checkout, with full artifact and aggregate builds passing. A local MCP projection supports current and legacy clients over stdio. The runtime can mount multiple local and compact C simulation routes under one authority, with immutable operation routing, durable mappings, receipt reconciliation and host-process recovery. Primary-source research and checked WoT descriptions support the design. Real adapters, complete commissioned firmware, production Harness integration and physical validation remain unfinished. The user goal remains active. [Progress and requirement audit](PROGRESS.md) records the evidence and remaining work.

Durable ordered procedures coordinate those routes with atomic child admission,
explicit restart continuation and checked CLI/MCP access. The latest complete
run passes all **643 tests**, with 131 inputs and compiler identity unchanged;
the evidence audit verifies 45,444 hashes across 29,534 files. Earlier passing
and failed runs remain preserved. The new
[PAT simulation qualification components](docs/pat-simulation-qualification.md)
include closed configuration/domain contracts, shared environment extraction,
an executable isolated fan worker, a catalog evidence gate and a bounded evidence
reducer/store. The corrected store/hook integration passes 46 focused tests with
fresh worker outputs; durable supervision and the public qualification service
remain unfinished. The pure I/O resource topology library now passes 21 focused tests;
the reviewed 26-test resource-admission stage awaits integration. The full run
includes the topology library, evidence store and latest evaluation-integrity fixes.
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
