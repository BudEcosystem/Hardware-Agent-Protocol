# Bud Hardware Model Standard — working draft 0.1

Status: proposed standard with an experimental local simulation runtime. “HMS” names this project; “MHS” refers to Anthropic's separate research preview. No wire compatibility or certification is claimed. Requirements using MUST describe what a conforming implementation would need to do; implementation coverage is recorded in the [progress audit](../PROGRESS.md). The draft remains subject to research and failure testing.

## Intended outcome

Bud Meta Harness agents discover, understand, operate, observe and manage heterogeneous physical systems through one semantic interface. The same interface supports human CLI users, deterministic programs, on-device agents, a local compute hub such as GB10, and optional remote agents. Device adapters preserve existing controller capabilities. Native firmware and controllers retain responsibility for their timing and physical protection functions.

The user's additional requirements make natural-language application creation,
experience-based learning and deterministic Programs as Tools (PATs) core system
behavior. Familiar contexts should execute eligible PATs without repeated planning
inference; unhandled contexts may require the agent. Known invalid inputs and
temporary resource or evidence unavailability follow explicit deterministic
refusal/recovery rules. Applications composed from
installed Arduino capabilities should not require a new user-written sketch.
See [prompt-to-PAT architecture](../docs/prompt-to-pat.md).

The managed scope includes device I/O, buses and peripherals, driver configuration
and lifecycle, and the compute, data, network and service resources of an optional
intelligence hub such as GB10. These form one dependency-aware resource graph;
see [I/O, driver and hub control](../docs/io-driver-hub-control.md). These are
required extensions, not features established by the current simulations.

Universal coverage is an extensibility requirement: the model is designed to permit direct, gateway and physical-retrofit representations across device classes. Each claimed device/action requires a useful binding and supporting evidence; an unsupported placeholder does not establish automation. An unsupported action MUST return an explicit unsupported capability, not a best-effort approximation. A chip without memory protection, an operating system, or an interpreter does not need to host an LLM or full network runtime. A manual knob requires an actuator and feedback path before software can control it. An unobservable physical result remains unverified.

A universal description cannot guarantee arbitrary physical tasks are achievable. Reach, available energy, observability, environmental conditions, vendor access and physical compatibility constrain execution. A device catalog entry is neither an installation assessment nor an assertion that devices can safely share a workspace.

## Deliverables and dependencies

| Deliverable | Present state | Evidence needed for completion |
|---|---|---|
| Research corpus | Expanded acquisition and full-reading passes underway | Primary sources locally archived; hashes, complete reading coverage and critical notes; explicit access gaps |
| Protocol and data model | Working draft | Independent review, schemas and wire fixtures covering every normative operation |
| Runtime and tool manager | Original local simulation runtime, checked CLI/SDK/MCP and finite procedure/PAT libraries | Production services, real providers, target crash/concurrency qualification and measured timings |
| Registry | Local persistent registry with admission, discovery/expiry and immutable binding history | Trust and federation exercised against real adapters; domain resource/provider integration |
| MCU support | Protocol/source research and native-tested framing component | Bounded executor and host bridge tested on at least AVR-class and modern MCU hardware |
| Harness integration | Native/PTC/Loader/AgentLoop checks at retained historical Harness/runtime pins | Production packaging, current-version integration and interrupted active-work recovery |
| Microscope retrofit | Commissioning design | Mechanical/electrical design matched to a specified microscope, calibration, physical tests |
| Home/lab/factory scenarios | Designed scenarios | Reproducible end-to-end traces, injected faults, domain-specific physical checks |
| Performance/universality | Targets and profiles | Benchmarks and a device/support matrix, no extrapolation from one simulator |

The original ten-part user objective remains open. An exhaustive claim over every article or every possible device is not verifiable; use a documented search matrix, bibliographic expansion and explicit coverage instead. Do not call a downloaded corpus fully read because text extraction succeeded.

## Research organization

`research/mhs/`, `research/protocols/`, `research/physical-ai/` and `research/laboratory/`, `research/constrained/` and `research/embedded/` contain acquired material, metadata and reading notes. `research/harness/` records local integration evidence. Research snapshots are reference material, never automatically executable dependencies. Review licenses before redistribution. Paid or unavailable standards remain gaps; summaries do not count as the full standard.

The specification is an original synthesis. Read [protocol comparison](../docs/protocol-landscape.md), [physical-AI comparison](../docs/physical-ai-landscape.md), [MHS source findings](../research/mhs/notes/findings.md), [harness integration](../docs/harness-integration.md) and [microscope design](../docs/microscope-retrofit.md) for evidence and limitations.
