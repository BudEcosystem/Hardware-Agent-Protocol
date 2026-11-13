# HMS End-to-End Master Plan: Research, Implementation, Verification and Testing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take HMS from a simulation-only prototype to a universal physical-AI system: any device, instrument or machine can be discovered, operated and observed by any model, agent or program through one semantic contract, with evidence for every claim, at single-device through fleet scale.

**Architecture:** One small semantic kernel (durable operations, typed observations, resource authority) with four things built on it: a *binding ladder* of adapters that reaches any device (native protocol → bridge → retrofit actuator → general manipulator), *Programs as Tools* (PAT) that turn one-time agent planning into deterministic reuse, a *hub layer* that manages models and compute as resources, and *federation* for scale. The runtime never calls a model; agents enter only through checked, authenticated surfaces.

**Tech Stack:** Python 3.12 (host runtime, `jsonschema` only in core), C11 (endpoint firmware; avr-gcc 7.3, arm-none-eabi-gcc 13), SQLite (authority journal), CMake (firmware), TypeScript/pnpm (Bud-Meta-Harness packages), pytest + hypothesis + libFuzzer + TLA+ (verification), simavr/QEMU (target-binary simulation), uv (dependency locking).

**Spec:** [`spec/00-scope.md`](../../../spec/00-scope.md) through [`spec/12-io-driver-boundary.md`](../../../spec/12-io-driver-boundary.md), plus [`docs/prompt-to-pat.md`](../../prompt-to-pat.md), [`docs/io-driver-hub-control.md`](../../io-driver-hub-control.md), [`docs/harness-integration.md`](../../harness-integration.md), [`docs/conformance-plan.md`](../../conformance-plan.md) and the requirement audit in [`PROGRESS.md`](../../../PROGRESS.md). This plan argues from those documents; executors read both.

## Global Constraints

Every task implicitly includes these. Values are copied from the spec or from the owner's standing instructions.

- **No stubs.** Every function and module ships complete and production-ready. No placeholder bodies, no mocks standing in for product code.
- **No duplicate code.** Search `hms/`, `hms_qualification/` and `protocol/` before writing anything. Reuse `hms/contracts.py` (`parse_json`, `canonical`, `identifier`, `ContractError`) and the checkers consolidated in Phase 0 Task 4.
- **Search hygiene.** Exclude `artifacts/` and `integration/` from every code search. They hold hundreds of stale copies of `hms/*.py`.
- **No code outside the core system.** Nothing lives only in `artifacts/`. A change is done when it is merged, tested in `tests/`, and reachable from a public surface or imported by one.
- **One authority path.** Every mutating surface (CLI, SDK, MCP, Harness tool, PAT, adapter) enters `Runtime.request`. No side doors.
- **The runtime never calls a model.** Planning and synthesis live in the agent host. They reach the runtime only through `proposal_put` and the other checked methods.
- **Never retry an effect that may have happened.** After dispatch, a missing reply becomes `outcome_unknown` and is reconciled.
- **Unsupported means refuse.** Return an explicit unsupported-capability error; never approximate.
- **Label every claim with its evidence tier** (T0–T5, defined below). A simulation pass is never reported as a physical result.
- **Retain failures.** A failed or timed-out run is recorded with its reproduction command, never deleted or overwritten.
- **Core dependencies stay minimal.** The core runtime depends on `jsonschema` (4.25.1 and its pinned transitive set) and nothing else. Protocol libraries live in per-adapter locked environments.
- **Compiler identity is deliberate.** `hms/pat_compiler.py::verify_compiler_identity` hashes 14 source files. Any edit to those files changes `compiler_digest()` and invalidates promoted PAT evidence. Such an edit must state the old and new digest in its commit message, and any PAT promoted under the old digest must be re-qualified.
- **Firmware rules:** no dynamic allocation, fixed buffers, bounded parser, every loop bounded, ASan/UBSan-clean on the native build before any target build.
- **Platform:** Linux only for the host runtime (Unix sockets with `SO_PEERCRED`).
- **MHS naming:** "HMS" is this project. "MHS" is Anthropic's closed preview. Claim no MHS compatibility until its schema is public and tested against.

## Review Focus

The five conditions the spec implies but no current test exercises, most likely first. Each is pinned to the task that owns the code.

1. **A real target binary has never executed.** Every firmware result is a host-native build or a link map. A timing or stack bug would surface only on the MCU. *Pinned by Phase 1 Task 3 (`test_target_sim_executes_scenarios`).*
2. **The 42 `hms/pat_io_*` modules have no tests in `tests/`.** A refactor could break qualification silently. *Pinned by Phase 0 Task 5 (`tests/qualification/`).*
3. **Real serial links drop, split and corrupt bytes mid-frame.** The simulation transport is a lossless socketpair. *Pinned by Phase 2 Task 2 (`test_serial_partial_and_corrupt_frames`).*
4. **Power loss mid-operation on a real device.** Boot-epoch and EEPROM logic are only fault-modelled. *Pinned by Phase 1 Task 4 (simulated reset at every cycle boundary) and Phase 2 Task 4 (USB port power cut).*
5. **Two agents with different authority under one Unix UID.** Today every process under one UID shares one principal. *Pinned by Phase 7 Task 1 (`test_delegation_scopes_are_independent`).*

---

## 1. How to read this plan

**Companion plan:** [`2026-11-13-hms-full-validation-plan.md`](2026-11-13-hms-full-validation-plan.md) defines how the system built here is validated: a simulated multi-device lab, the physical controller, real stations and the coverage ledger. Tool trials for it are recorded in [`docs/validation/tool-trials-2026-11-13/`](../../validation/tool-trials-2026-11-13/README.md).

This is a master plan for thirteen phases. Per the planning skill's scope rule, a system this size is split into one plan per subsystem.

- **Phases 0 and 1 are written at step level here.** They can be executed immediately.
- **Phases 2–12 are written at task level:** files, interfaces, tests and exit evidence. Each gets its own step-level plan in `docs/superpowers/plans/` when it starts, because its exact signatures depend on what earlier phases produce.
- **Decisions are numbered D1–D12** (section 3). They are the choices an implementer could not make alone. Changing one is a plan change, not an implementation detail.

## 2. Starting point (verified 2026-11-13)

| Area | What exists | Gap |
|---|---|---|
| Host runtime | `hms/` ~21K lines; 14 public methods over a Unix socket; SQLite journal; three simulation backends | Simulation only |
| Tests | 866 unittest tests pass (512 s) | No tests for `pat_io_*`; one of 81 files touches `hms_qualification` |
| PAT | Compiler, catalog, execution, qualification libraries | Not imported by `runtime.py`, `cli.py` or `mcp.py`; no public method |
| Firmware | Finite endpoint cross-links for ATmega328P at 21,778 flash bytes | Never executed on a target or simulator. Standing firmware is 39,186 bytes, 6,930 over the allowance |
| Isolated candidates | 105 increments in `artifacts/implementation/` (26 GB) | Two adopted. Intent handoff, standing host, hub recovery and AVR link integration are not |
| Harness | Nine `hardware_*` tools as a patch on three frozen worktrees | Not in the live checkout |
| Reproducibility | None | No git, no `pyproject.toml`, no lockfile. Tests need a prebuilt binary under `artifacts/`; `hms/registry.py` loads a schema from `research/` |
| Local bench | RTX 3080 (10 GB), 62 GB RAM, gcc, clang, cmake, uv, pytest, hypothesis | No MCU attached. simavr, QEMU and avr-gcc are not installed (all available from apt) |
| MHS | Closed preview since August 2026; no public schema or release date | Nothing to be compatible with yet |

## 3. Strategic decisions

**D1. Vertical slices before horizontal polish.** Each milestone ends in something demonstrable end to end. The project's history shows the cost of the alternative: seven firmware refactors and eight storage candidates without one physical run.

**D2. Git and CI replace full-tree copies.** A candidate is a branch. Its evidence is a CI receipt plus a content-addressed manifest. Retained failures remain, as receipts, not as 60 MB tree copies.

**D3. Evidence tiers.** Every result is labelled T0–T5 (section 5). This keeps the project's honesty rule and makes progress measurable.

**D4. Execute the real firmware in an instruction-level simulator before buying hardware.** simavr runs the actual AVR ELF with cycle counts, UART, timers, EEPROM and resets. This closes the largest evidence gap with no hardware.

**D5. Stop shrinking the standing firmware for the ATmega328P.** Split the endpoint into two profiles:
- *Finite profile* on the ATmega328P (Uno R3). It already fits.
- *Standing profile* on the ATmega2560 (Arduino Mega, 256 KB flash, same avr-gcc and simavr) first, then a Cortex-M port (RP2040 or Uno R4).

The 328P stays supported for finite operations. A reduced standing kernel for the 328P is reopened only if a real deployment needs it.

**D6. A stuck optimization triggers a design decision.** Three consecutive failed attempts at the same fit or deadline limit stop the line. The next step is a written decision: change the requirement, change the design, or change the target.

**D7. Protected control capacity comes from the operating system first.** Use a dedicated fixed-size filesystem per storage class (control and evidence) so the OS enforces both the cap and the reservation, with SQLite's page limit inside it. The custom chunk-store line (eight candidates, unadopted) is parked. It reopens only if a measured requirement fails under this approach.

**D8. Adapters run out of process behind one SDK, and a conformance kit decides support.** "Any device" becomes a procedure anyone can follow: write an adapter, run the kit, publish the result table.

**D9. Every adapter ships with a software twin.** A twin is a protocol-level simulator of the device. It lets every adapter reach T1 in CI before hardware exists.

**D10. Standing applications use installed parameterized kernels before a general bytecode VM.** Kernels: hysteresis, threshold alarm, timer, edge trigger, bounded PI. A VM is built only when three requested applications cannot be expressed as kernel compositions.

**D11. One authority per site; scale by federation.** A single-writer SQLite journal per site is kept. Fleets scale by adding sites that exchange catalog summaries, never by replicating one journal across writers. A native (Rust) journal core is a gated option, taken only if measured single-site budgets fail after profiling.

**D12. The hand is the last rung, not the foundation.** A dexterous manipulator is a first-class adapter under the same contract. Its job is coverage of devices with no interface, and bootstrapping: procedures learned through it *graduate* to a retrofit actuator or a native binding.

## 4. Target architecture

```
 Agents and programs:  Bud agents | local LLM on hub | remote agents | humans | scripts
        │
 Surfaces:   Harness native tools + PTC | MCP (stdio, HTTP) | hctl CLI | Python/TS SDK
        │                (authenticated transport; per-agent delegation tokens)
        ▼
 ┌─────────────────────────── Site runtime (one authority) ───────────────────────────┐
 │ Registry      types, instances, bindings, presence, grants, resource graph         │
 │ Journal       replay keys, claims/fences, operation states, events (SQLite)        │
 │ Procedures    bounded ordered sequences                                            │
 │ PAT           intent → proposal → qualification → catalog → deterministic router   │
 │ Standing      long-running applications with renewable local authority             │
 │ Data plane    watch cursors, data references, artifact store, shared-memory rings  │
 │ Stop service  separate bounded path, not behind the journal writer lock            │
 └───────────────┬───────────────────────────────────────────────┬────────────────────┘
                 │ adapter SDK (out-of-process workers)          │ federation
                 ▼                                               ▼
 Binding ladder                                          Other sites / fleet catalog
   1 native protocol   serial endpoint, Firmata, SCPI, Modbus, OPC UA, MQTT, ROS 2
   2 bridge            vendor SDK, GUI automation, file drop
   3 retrofit actuator fixed "finger" on a knob or button, with feedback
   4 manipulator       learned policy on an arm or hand, vision-verified
                 │
 Hub resources   CPU/GPU jobs, pinned models, perception stages, storage, network
                 │
 Controllers     MCU firmware, PLCs, drives: own timing, limits and stopping
```

**Public method families** (all in `schemas/local-api.schema.json`, all through `Runtime.request`):

| Family | Methods | Phase |
|---|---|---|
| Core (exists) | `discover`, `describe`, `observe`, `namespace`, `prepare`, `invoke`, `operation`, `cancel`, `events` | — |
| Procedures (exists) | `procedure_submit`, `procedure_status`, `procedure_resume`, `procedure_cancel`, `procedure_events` | — |
| PAT | `pat_publish`, `pat_evaluate`, `pat_transition`, `pat_describe`, `pat_list`, `pat_run`, `pat_status`, `pat_cancel`, `pat_resume`, `pat_events` | 3 |
| Intent | `intent_put`, `intent_get`, `proposal_put` | 3 |
| Qualification | `qualification_submit`, `qualification_status` | 3 |
| Standing | `standing_prepare`, `standing_open`, `standing_mutate`, `standing_status`, `standing_collect`, `standing_revoke` | 4 |
| Data | `watch`, `dataref_describe`, `dataref_read` | 6 |
| Authority | `stop`, `delegation_issue`, `delegation_revoke`, `approval_request`, `approval_status` | 7 |
| Lifecycle | `driver_change`, `driver_status` | 5 |
| Hub | `job_submit`, `job_status`, `job_cancel` | 8 |

## 5. Evidence tiers and definition of done

| Tier | Meaning | Example | Can claim |
|---|---|---|---|
| T0 | Static: schema, types, pure functions, formal model | Canonicalization vectors; TLA+ model check | "specified and checked" |
| T1 | Host simulation: real processes, simulated device | Daemon + CLI + C endpoint over a socketpair; software twin | "passed in simulation" |
| T2 | Target-binary simulation: the real ELF in an instruction-level simulator | Uno firmware in simavr with injected resets | "target binary executes; simulated timing" |
| T3 | Bench hardware in the loop, with independent measurement | Real Uno, loopback wiring, logic analyzer | "passed on named hardware" |
| T4 | Physical scenario with the real process | Microscope focus scan; enclosure temperature control | "scenario demonstrated" |
| T5 | Fleet and soak | 72-hour run, many devices, injected faults | "operational evidence" |

**A task is done when:**
1. Its code is merged on the main branch with no stubs.
2. Its tests are in `tests/` (or the adapter's `tests/`) and pass in CI at the stated tier.
3. It is reachable from a public surface, or imported by code that is.
4. The requirement-to-evidence table (`docs/evidence-matrix.md`, created in Phase 0) has a row updated to one of: `not implemented`, `implemented untested`, `failed`, `passed T<n>`, `not applicable (reason)`.
5. Documentation for any new public method exists in the spec chapter that owns it.

## 6. Milestones and phase order

| Milestone | Demonstrates | Phases | Highest tier |
|---|---|---|---|
| **M0 Reproducible** | Clean clone → install → all tests pass in CI | 0 | T1 |
| **M1 Real binary runs** | `hctl invoke` drives the actual AVR ELF in simavr, through resets | 1 | T2 |
| **M2 First physical effect** | `hctl invoke` sets a PWM pin on a real Uno; a second instrument measures it | 2 | T3 |
| **M3 PAT end to end** | Prompt → proposal → qualification → promotion → repeat run with zero planning calls | 3, 9a | T2 |
| **M4 No-sketch application** | "Keep the enclosure between these temperatures" runs on a real Arduino with no user sketch | 4 | T4 |
| **M5 Any protocol** | Three adapter families pass the conformance kit; home and factory scenarios run with fault injection | 5, 6, 10 | T1 → T3 |
| **M6 Microscope** | Focus retrofit scan with image lineage | 10 | T4 |
| **M7 Hub and learned control** | Local model on the hub; perception stage in a PAT; manipulator binding in simulation | 8 | T1 → T3 |
| **M8 Scale** | Remote authenticated agents, multi-site federation, 10k-device inventory, 72-hour soak | 7, 11 | T5 |
| **M9 Standard 1.0-rc** | Frozen spec, public conformance suite, second implementation | 12 | — |

**Dependencies:**

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 4 ──► Phase 10 (scenarios)
   │           │                       ▲
   │           └──► Phase 5 (adapters) ┼──► Phase 6 (data) ──► Phase 8 (hub, models)
   └──► Phase 3 (PAT) ─────────────────┘                          │
   └──► Phase 7 (authority) ──────────────► Phase 11 (scale) ──► Phase 12 (standard)
   └──► Phase 9 (Harness) runs alongside 3, 6, 7, 8
Research track R runs throughout; each lane gates a named phase.
```

Phases 3, 5 and 7 can run in parallel after Phase 0. Phase 2 needs hardware (section 10).

**Sizing** (agent-driven development with one human reviewer; estimates, not commitments): Phase 0: 1–2 weeks. Phase 1: 2 weeks. Phase 2: 2 weeks after hardware arrives. Phase 3: 4–5 weeks. Phase 4: 4 weeks. Phase 5: 6–8 weeks for the SDK plus the first five adapters. Phases 6–8: 3–5 weeks each. Phase 9: continuous. Phase 10: 6+ weeks, gated on hardware. Phases 11–12: 6–8 weeks. M4 is reachable in roughly three months; M9 in nine to twelve.

---

## 7. Research track (R)

The existing rule stays: acquisition and reading are tracked separately, with hash receipts, and partial coverage is stated with numbers. One thing changes: **research is scheduled just in time.** Each lane names the phase it gates and the decision it must settle. A lane is complete when its decision record is written, not when a backlog is empty.

| Lane | Sources | Decision to settle | Gates |
|---|---|---|---|
| R1 Target simulation | simavr source and docs; QEMU Cortex-M; Renode | Which peripherals are modelled faithfully enough for T2 claims; what T2 cannot claim | Phase 1 |
| R2 Serial and USB reality | ATmega16U2 USB-serial firmware, CDC-ACM, Linux termios, DTR auto-reset | Reset-on-open behaviour, latency timer, framing under loss | Phase 2 |
| R3 PAT learning | Voyager and LRLL (done); AutoSkill, Skill++ (queued); program induction; novelty detection and abstention | Applicability predicates; promotion evidence; what counts as a novel context | Phase 3 |
| R4 Embedded control kernels | Firmata scheduler, ConfigurableFirmata, PLCopen function blocks, IEC 61499, TinyML runtimes | Kernel set and parameter envelopes for D10; VM criteria | Phase 4 |
| R5 Adapter protocols | SCPI-99 (2,780 of 42,293 lines read), Modbus security, OPC UA Parts 2–8 and PubSub, SiLA 2 feature XML, Matter, Home Assistant and ESPHome builds, ROS 2 actions and ros2_control | Per-binding guarantee table: what each acknowledgement proves | Phase 5 (one sub-lane per adapter) |
| R6 Streams and zero-copy | iceoryx2, Zenoh, DDS QoS, V4L2/UVC, GenICam, shared-memory layouts | Stream contract; ring layout; backpressure policy | Phase 6 |
| R7 Capability security | Macaroons, Biscuit, UCAN, SPIFFE; OSCORE/EDHOC stacks (specs already read); NIST SP 800-82 | Token format; remote transport; MCU trust boundary | Phase 7 |
| R8 Learned control and manipulation | GR00T N1.x, π0 family, OpenVLA-OFT, SmolVLA, ACT, LeRobot; dexterous-hand hardware; teleoperation data | Action-chunk admission; termination monitors; manipulator binding (D12) | Phase 8 |
| R9 Hub deployment | GB10/DGX Spark porting and known-issues pages; Jetson; model servers; GPU memory accounting | Hub resource model; ARM64 dependency closure | Phase 8 |
| R10 Formal methods and simulation testing | TLA+ practice; deterministic simulation testing (FoundationDB, TigerBeetle); Jepsen analyses | Which protocols get a formal model; simulation-testing harness design | Phases 0–1, 11 |
| R11 Machinery and safety regulation | ISO 10218, ISO 13849, IEC 61508 overviews; EU Machinery Regulation (applies 2027); NIST OT security | What HMS must never claim; documentation a deployer needs | Phases 7, 12 |
| R12 MHS watch | Anthropic announcements; partner releases (LeRobot, Universal Robots, Raspberry Pi, Tecan); any public schema | Bridge or alignment once a schema is public | Phase 12; checked monthly |
| R13 Microscopy | OpenFlexure (done), Micro-Manager, actual instrument manuals | Retrofit design for the owner's microscope | Phase 10 |

**Each lane delivers:** an acquisition manifest, reading receipts, a critique note, and a decision record at `docs/decisions/R<n>-<topic>.md` with the alternatives rejected and why.

---

## 8. Phase 0: Foundation (step-level)

**Outcome:** a clean clone installs and passes every test in CI; nothing depends on `artifacts/` or `research/` at run time; the evidence store no longer copies trees. Milestone M0.

### File structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Package metadata, pinned dependencies, pytest config and markers |
| `.gitignore`, `.gitattributes` | Keep `artifacts/`, `research/**/raw/`, build output and caches out of git |
| `schemas/vendor/td-schema-1.1.json`, `schemas/vendor/mcp-2026-07-28.schema.json` | Schemas the code and tests load, moved out of `research/` |
| `hms/paths.py` | The one place that resolves repository-relative resource paths |
| `hms/checks.py` | The one implementation of `require`, `closed`, `integer`, `same` |
| `scripts/build_native.py` | Builds test binaries (`endpoint-scenarios-pipe`, `retention_scan.so`) into `build/` |
| `scripts/ci.py` | CI entry point with tiers `fast`, `full`, `target`, `nightly` |
| `scripts/evidence.py` | Content-addressed evidence store: `put`, `ingest`, `verify` |
| `tests/qualification/` | Tests for `hms/pat_io_*` and `hms_qualification/` |
| `docs/evidence-matrix.md` | Requirement → evidence table |
| `docs/adoption-backlog.md` | Triage of the 105 isolated increments |

### Task 1: Version control and dependency lock

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `.gitattributes`
- Modify: `.gitignore`

**Interfaces:**
- Produces: installable package `hms` (also packages `hms_qualification`, `protocol`); console script `hctl = hms.cli:main`; pytest markers `fast`, `process`, `crash`, `target`, `hil`, `slow`.

- [ ] **Step 1: Initialize git and ignore bulk data**

Add to `.gitignore`: `artifacts/`, `build/`, `evidence/objects/`, `research/**/raw/`, `research/**/repos/`, `*.so`, `.venv/`. Then:

```bash
cd /home/bud/Desktop/bud/hms && git init -b main
git add .gitignore && git commit -m "chore: initialize repository"
```

- [ ] **Step 2: Remove committed bytecode from the tree**

```bash
find hms hms_qualification protocol tests scripts -name __pycache__ -type d -prune -exec rm -rf {} +
```

Expected: `find . -name "*.pyc" -not -path "./artifacts/*" -not -path "./research/*" | wc -l` prints `0`.

- [ ] **Step 3: Write `pyproject.toml`**

Project name `hms`, version `0.1.0`, `requires-python = ">=3.12"`. Core dependencies: `jsonschema==4.25.1`. Optional group `test`: `pytest`, `pytest-xdist`, `hypothesis`, `coverage`, `mcp==1.26.0`, `anyio`. Optional group `research`: `requests`, `beautifulsoup4`. Add `[tool.setuptools.packages.find] include = ["hms*", "hms_qualification*", "protocol*"]` and empty `protocol/__init__.py` and `protocol/serial/__init__.py` files so `protocol.serial.frame` imports without the repository root on `sys.path`. Under `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `pythonpath = ["tests"]` (tests import each other as siblings), and the six markers.

- [ ] **Step 4: Lock and install into a fresh environment**

```bash
uv lock && uv venv .venv && uv pip install --python .venv/bin/python -e ".[test]"
```

Expected: `uv.lock` exists; `.venv/bin/python -c "import hms, protocol.serial.frame"` exits 0 from `/tmp`.

- [ ] **Step 5: Commit the source tree**

```bash
git add -A && git commit -m "chore: add packaging, lockfile and source tree"
```

Expected: `git status --short | wc -l` prints `0`; `du -sh .git` is under 100 MB.

### Task 2: Remove run-time dependence on `research/` and `artifacts/`

**Files:**
- Create: `hms/paths.py`, `schemas/vendor/td-schema-1.1.json`, `schemas/vendor/mcp-2026-07-28.schema.json`, `scripts/build_native.py`, `tests/test_paths.py`
- Modify: `hms/registry.py:41`, `hms/pat_compiler.py:67`, `hms/pat_evidence_memo.py:40`, `hms/synthetic_io_installation.py:41`, `hms/pat_simulation_worker.py:67`, `tests/test_mcp.py:49`, `tests/test_endpoint_mcp.py:33,205`, `tests/test_endpoint_cli.py:35`, `tests/test_endpoint_binding.py:22`, `tests/test_multi_adapter.py:34-35`, `tests/test_io_resource_admission.py:29,434`, `tests/test_multi_cli.py:82`, `hms_qualification/supervisor/retention_native.py:14`

**Interfaces:**
- Produces: `hms.paths.REPO_ROOT: Path`; `hms.paths.schema_path(name: str) -> Path` (resolves under `schemas/`, raises `FileNotFoundError` for an unknown name); `hms.paths.build_path(name: str) -> Path` (resolves under `build/`).
- Produces: `python3 scripts/build_native.py [--target endpoint-scenarios-pipe|retention-scan|all]` writing to `build/`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py
import hashlib, unittest
from hms.paths import REPO_ROOT, schema_path

class PathsTest(unittest.TestCase):
    def test_td_schema_is_vendored_with_original_bytes(self):
        data = schema_path("vendor/td-schema-1.1.json").read_bytes()
        self.assertEqual(len(data), 34642)

    def test_unknown_schema_is_refused(self):
        with self.assertRaises(FileNotFoundError):
            schema_path("vendor/missing.json")

    def test_no_runtime_module_reads_research_or_artifacts(self):
        offenders = [p.name for p in (REPO_ROOT / "hms").glob("*.py")
                     if "research/" in p.read_text() or "artifacts/" in p.read_text()]
        self.assertEqual(offenders, [])
```

The 34,642-byte size is the value `tests/test_io_resource_admission.py:29` already pins for the TD schema.

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: hms.paths`.

- [ ] **Step 3: Copy the two schemas byte for byte and implement `hms/paths.py`**

```bash
mkdir -p schemas/vendor
cp research/protocols/wot-artifacts/td-schema-1.1.json schemas/vendor/td-schema-1.1.json
cp research/mcp/raw/schema__2026-07-28__schema.json schemas/vendor/mcp-2026-07-28.schema.json
```

Replace each listed `research/...` path with `schema_path(...)`. `hms/pat_compiler.py:67` lists the TD schema among the files hashed into the compiler identity: change that entry to `schemas/vendor/td-schema-1.1.json`. The bytes are identical, but the recorded path changes, so `compiler_digest()` changes: state the old and new digest in the commit message.

- [ ] **Step 4: Build test binaries from source instead of reading `artifacts/`**

`scripts/build_native.py` compiles `tests/endpoint_scenarios_pipe.c` with `protocol/endpoint/{endpoint,link,scenario_fixture}.c` and `protocol/serial/frame.c` using `gcc -std=c11 -Wall -Wextra -Werror -O2` into `build/endpoint-scenarios-pipe`, and builds `hms_qualification/supervisor/retention_scanmodule.c` into `build/retention_scan.so`. Replace the four `BINARY = ROOT / 'artifacts/...'` constants with `build_path("endpoint-scenarios-pipe")`. Move the fixture directory read at `tests/test_multi_adapter.py:35` into `tests/fixtures/multi-adapter-design-review/`. Point `tests/test_multi_cli.py:82` at a `tempfile.mkdtemp()` directory.

`hms_qualification/supervisor/retention_native.py` pins the `.so` by SHA-256. Change line 14 (`BINARY = Path(__file__).with_name('retention_scan.so')`) to `build_path("retention_scan.so")`. Keep the SHA-256 check: record the digest produced by the pinned compiler in `hms_qualification/supervisor/retention_scan.sha256`, and have `build_native.py` fail when the built digest differs.

- [ ] **Step 5: Run the full suite from a clean clone**

```bash
git clone . /tmp/hms-clean && cd /tmp/hms-clean && uv venv .venv \
  && uv pip install --python .venv/bin/python -e ".[test]" \
  && .venv/bin/python scripts/build_native.py --target all \
  && .venv/bin/pytest -q
```

Expected: `866 passed` plus the three new tests, zero failures, in roughly nine minutes. `artifacts/` and `research/` do not exist in the clone. Run it serially: the suite contains deadline-bound tests that have timed out under load before.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "build: vendor schemas and build test binaries from source"
```

### Task 3: CI entry point and test tiers

**Files:**
- Create: `scripts/ci.py`, `.github/workflows/ci.yml`, `docs/evidence-matrix.md`
- Modify: `tests/*.py` (add markers), `scripts/check_runtime.py` (call the shared runner)

**Interfaces:**
- Produces: `python3 scripts/ci.py <tier>` with tiers `fast` (lint, type check, `-m fast`), `full` (everything except `target`, `hil`), `target` (`-m target`), `nightly` (full + fuzz + simulation-testing seeds). `--select <path>` narrows the test selection. Each run writes `build/ci/<tier>-<utc>.json` with: git commit, lockfile hash, test counts, duration, and failures with reproduction commands, and prints that path (relative to the repository root) as its last line of stdout.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ci_receipt.py
import json, subprocess, sys, unittest
from hms.paths import REPO_ROOT

class CiReceiptTest(unittest.TestCase):
    def test_fast_tier_writes_a_receipt_with_commit_and_counts(self):
        out = subprocess.run([sys.executable, "scripts/ci.py", "fast", "--select", "tests/test_paths.py"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        receipt = json.loads((REPO_ROOT / out.stdout.strip().splitlines()[-1]).read_text())
        self.assertEqual(receipt["tier"], "fast")
        self.assertRegex(receipt["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(receipt["tests"]["failed"], 0)
        self.assertGreaterEqual(receipt["tests"]["passed"], 3)
```

- [ ] **Step 2: Run it to confirm it fails** — `.venv/bin/pytest tests/test_ci_receipt.py -v` → FAIL (`scripts/ci.py` missing).

- [ ] **Step 3: Implement `scripts/ci.py`**

It shells out to `ruff check --select F,E9` (correctness rules only; the existing code is not style-clean and style rules are out of scope), `mypy hms/paths.py hms/checks.py` (the typed surface grows per phase) and `pytest` with `--junitxml`, then writes the receipt. Only the `fast` tier uses `pytest -n auto`; every other tier runs serially because of the deadline-bound tests. A failed run still writes a receipt with `"status": "failed"`; it never deletes an earlier one.

- [ ] **Step 4: Mark tests by tier**

`fast`: pure tests under 1 s with no subprocess. `process`: tests that start a daemon or the C endpoint. `crash`: tests using `tests/*_crash_driver.py`. Verify: `.venv/bin/pytest -m fast -q` finishes in under 120 s.

- [ ] **Step 5: Create `docs/evidence-matrix.md`**

One row per ID in `docs/conformance-plan.md` (AUTH-01 … SCALE-01, MICRO-01 … MICRO-08), with columns `Status`, `Tier`, `Evidence (test or receipt)`, `Limit`. Fill it from the "Boundary now exercised" table in the conformance plan.

- [ ] **Step 6: Run and commit** — `python3 scripts/ci.py full` → status `passed`. Commit: `ci: add tiered runner, receipts and evidence matrix`.

### Task 4: Consolidate duplicated checkers

**Files:**
- Create: `hms/checks.py`, `tests/test_checks.py`
- Modify: the 30 modules across `hms/` and `hms_qualification/` that define their own module-level `require` (list them with `grep -rln "^def require" hms hms_qualification`)

**Interfaces:**
- Produces: `hms.checks.Checker(error_type: type[Exception], default_code: str)` with methods `require(condition, code=None, detail=None)`, `closed(value, fields, code=None)`, `integer(value, minimum=0, maximum=SAFE_INTEGER, code=None)`, `same(left, right, code=None)`. Each module binds one instance: `_check = Checker(PatError, "PAT_INVALID_ARTIFACT")`, then `require = _check.require`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checks.py
import unittest
from hms.checks import Checker

class E(Exception):
    def __init__(self, code, detail=None): self.code, self.detail = code, detail

class CheckerTest(unittest.TestCase):
    def setUp(self): self.c = Checker(E, "BAD")

    def test_require_raises_bound_error_with_default_code(self):
        with self.assertRaises(E) as ctx: self.c.require(False)
        self.assertEqual(ctx.exception.code, "BAD")

    def test_closed_rejects_missing_and_extra_fields(self):
        self.c.closed({"a": 1}, {"a"})
        for bad in ({}, {"a": 1, "b": 2}, [("a", 1)]):
            with self.assertRaises(E): self.c.closed(bad, {"a"})

    def test_integer_rejects_bool_float_and_out_of_range(self):
        self.assertEqual(self.c.integer(5), 5)
        for bad in (True, 5.0, -1, 2**53):
            with self.assertRaises(E): self.c.integer(bad)

    def test_same_distinguishes_one_from_one_point_zero(self):
        self.c.same(1, 1)
        with self.assertRaises(E): self.c.same(1, 1.0)
```

The `1` versus `1.0` case is the project's existing rule that canonical JSON must not let an integral float borrow an integer's validation result.

- [ ] **Step 2: Confirm failure**, **Step 3: implement `hms/checks.py`**, **Step 4: confirm pass.**

- [ ] **Step 5: Replace the duplicates one module per commit**

For each module: bind a `Checker`, delete the local definitions, run that module's tests. Behaviour must not change: before each replacement, diff the local helper against `Checker` and keep any stricter check as a parameter. Modules in the compiler identity set change `compiler_digest()`: state the old and new digests in the final commit message of this task.

- [ ] **Step 6: Verify and commit**

Run: `grep -rln "^def require" hms hms_qualification | wc -l` → `0` (`Checker.require` is a method, and modules bind it by assignment). `python3 scripts/ci.py full` → passed. Commit: `refactor: consolidate duplicated checkers into hms/checks.py`.

### Task 5: Bring qualification tests into the suite

**Files:**
- Create: `tests/qualification/` (one test module per `pat_io_*` layer and per `hms_qualification` subpackage), `tests/qualification/README.md`
- Source: the newest passing test file for each module under `artifacts/implementation/pat-io-*/` and `artifacts/implementation/pat-qualification-supervisor/tests/`

**Interfaces:**
- Consumes: `hms.pat_io_group_worker.run_io_group`, `hms.pat_io_group_history.inspect_io_group`, `hms_qualification.supervisor.qualification_supervisor`, `hms_qualification.evidence.reducer`.
- Produces: marker `slow` on the 30-case worker test (about 58 s).

- [ ] **Step 1: Inventory.** For each of the 42 `hms/pat_io_*.py` modules and each `hms_qualification/` subpackage, record in `tests/qualification/README.md` the artifact increment whose tests cover it and the pass count that increment reported.
- [ ] **Step 2: Copy each test module, fix imports to the installed packages, and replace fixture paths under `artifacts/` with generated or `tests/fixtures/` data.** Large retained capture fixtures (`project/tests/data/io-*`, about 7,900 files per copy) are regenerated by the worker in a session-scoped fixture, not committed.
- [ ] **Step 3: Run:** `.venv/bin/pytest tests/qualification -q`. Expected: every module in the inventory has at least one passing test; totals match the inventory or each difference is explained in the README.
- [ ] **Step 4: Add a coverage gate.** `scripts/ci.py full` fails when any `hms/*.py` or `hms_qualification/**/*.py` file has zero line coverage.
- [ ] **Step 5: Commit** — `test: bring qualification and pat_io tests into the main suite`.

### Task 6: Content-addressed evidence store and adoption backlog

**Files:**
- Create: `scripts/evidence.py`, `tests/test_evidence_store.py`, `docs/adoption-backlog.md`, `evidence/README.md`

**Interfaces:**
- Produces: `python3 scripts/evidence.py put <dir> --run <id>` → writes `evidence/runs/<id>.json` (`[{path, sha256, size}]`) and stores each unique file once at `evidence/objects/<sha256[:2]>/<sha256>`; `ingest <artifacts-subdir>` → the same for an existing increment, without modifying it; `verify <id>` → re-hashes and exits non-zero on any mismatch.

- [ ] **Step 1: Failing test** — `put` of a directory containing two identical files stores one object and a two-entry manifest; `verify` passes; flipping one byte in the object makes `verify` exit 1 and name the path.
- [ ] **Step 2–4: Confirm failure, implement, confirm pass.**
- [ ] **Step 5: Ingest, without deleting anything.** Run `ingest` on the five largest increments and report the deduplicated size. **Do not remove `artifacts/` content.** Its audits hash those files; removal needs the owner's explicit approval after a verified ingest.
- [ ] **Step 6: Write `docs/adoption-backlog.md`.** Classify all 105 increments:

| Class | Increments | Action |
|---|---|---|
| Adopt | `avr-link-integration` (Phase 1), `prompt-intent-handoff` (Phase 3), `standing-host-*` (Phase 4), `owned-hub-*` (Phase 8), `io-lifecycle-settlement` (Phase 5), `pat-integer-canonical` if not already merged | Merge through the normal branch → tests → CI path |
| Park | The storage line (`fixed-block-storage` … `compact-bitmap-store`, `existing-state-replacement`), 328P standing-fit line | Reopen only under D5, D6 or D7 criteria |
| Historical | Completed PAT I/O history increments already installed | Keep the manifest; no action |

- [ ] **Step 7: Commit** — `chore: add evidence store and adoption backlog`.

**Phase 0 exit gate (M0):** a fresh clone passes `scripts/ci.py full`; `grep -rn "artifacts/\|research/" hms/ hms_qualification/` returns nothing; every `hms/` module has test coverage; `docs/evidence-matrix.md` and `docs/adoption-backlog.md` exist.

---

## 9. Phase 1: The real target binary runs (step-level)

**Outcome:** the unmodified firmware ELF executes in simavr and is driven through the full host stack, including resets and EEPROM persistence. Milestone M1, tier T2.

### File structure

| File | Responsibility |
|---|---|
| `firmware/CMakeLists.txt`, `firmware/cmake/avr-atmega328p.cmake`, `firmware/cmake/avr-atmega2560.cmake` | Firmware build; one toolchain file per MCU |
| `protocol/platform/avr_runtime.{c,h}`, `avr_usart.{c,h}` | Adopted from `avr-link-integration`: main loop, UART RX/TX with Timer1 clock and boot reservation |
| `firmware/drivers/avr_gpio.c`, `avr_pwm.c`, `avr_adc.c`, `drivers.h` | Installed primitives implementing the endpoint callback table on real registers |
| `firmware/apps/finite_328p.c` | Composition root for the finite profile |
| `tools/simavr_host/simavr_host.c` | Runs an ELF in simavr; exposes UART as a socket and pins/ADC/reset on a control socket |
| `tests/support/simavr.py` | Python wrapper `SimAvr` |
| `hms/installations.py`, `hms/endpoint_binding.py` | New installation kind `compact-target-sim` |
| `tests/test_target_sim.py` | T2 tests |

### Task 1: Toolchain and firmware build

**Interfaces:**
- Produces: `cmake --preset avr-328p && cmake --build --preset avr-328p` → `build/firmware/avr-328p/hms_finite_328p.elf`; a size check that fails the build above 30,720 flash bytes (the Uno's 32,256 minus a 1,536-byte margin) or above 1,536 bytes of static SRAM.

- [ ] **Step 1:** Install pinned tools: `sudo apt-get install -y gcc-avr avr-libc simavr libsimavr-dev avrdude`. Record versions in `firmware/TOOLCHAIN.md`. Apt provides avr-gcc 7.3.0 (Atmel 3.7.0); the earlier link results used the Arduino 7.3.0 tarball. Build with both once and record the size difference.
- [ ] **Step 2:** Adopt `avr_runtime.{c,h}` and `avr_usart.{c,h}` from `artifacts/implementation/avr-link-integration/project/protocol/platform/` together with its `production-factorization.patch`. Diff every adopted file against the current `protocol/` copy first and keep the newer logic.
- [ ] **Step 3:** Bring the eleven register-model cases from that increment into `tests/` as native tests. Run under ASan/UBSan. Expected: 11 pass.
- [ ] **Step 4:** Write the CMake build and size gate. Expected: the ELF links near the recorded 21,778 flash bytes and 1,343 static SRAM bytes; the gate passes.
- [ ] **Step 5:** Commit — `firmware: add CMake build for the finite ATmega328P profile`.

### Task 2: Real drivers for installed primitives

**Interfaces:**
- Consumes: the endpoint callback table in `protocol/endpoint/endpoint.h`.
- Produces: `hms_drivers_init(void)`; primitives `gpio_write(pin, level)`, `gpio_read(pin)`, `pwm_set(channel, duty_u8)`, `adc_read(channel) -> u16`. Pin map for the Uno: PWM on Timer2 only (D3 = OC2B, D11 = OC2A). **Timer1 is owned by the clock and USART0 by the link** (`spec/12`), so D9/D10 PWM and D0/D1 are refused with `UNSUPPORTED`.

- [ ] **Step 1: Failing native test** against the register model: `gpio_write(13, 1)` sets `PORTB5` and `DDRB5`; `pwm_set` on a Timer1 pin returns `UNSUPPORTED` and leaves `TCCR1A/B` untouched; `adc_read` waits for `ADSC` to clear for at most a fixed iteration count and returns a timeout status beyond it.
- [ ] **Step 2–4:** Confirm failure, implement, confirm pass under ASan/UBSan.
- [ ] **Step 5:** Record declared effects in the type bundle. Per `spec/12`, `gpio_read` on a PWM pin and `adc_read` both change shared state, so their action contracts list those resources.
- [ ] **Step 6:** Commit.

### Task 3: simavr host and the T2 test

**Interfaces:**
- Produces: `simavr_host --mcu atmega328p --freq 16000000 --elf <path> --eeprom <file> --uart-fd <n> --control <socket>`. Control commands (one JSON line each): `{"op":"reset"}`, `{"op":"power_cycle"}`, `{"op":"adc","channel":0,"millivolts":2500}`, `{"op":"pin","port":"B","bit":5}` → `{"level":1}`, `{"op":"pwm","timer":2,"channel":"B"}` → `{"duty":128}`, `{"op":"cycles"}` → `{"cycles":N}`, `{"op":"run_until_cycle","cycle":N}`.
- Produces: `tests.support.simavr.SimAvr(elf, eeprom_path)` with `.uart_fd`, `.reset()`, `.power_cycle()`, `.set_adc(channel, millivolts)`, `.pin(port, bit)`, `.pwm(timer, channel)`, `.cycles()`, `.run_until_cycle(n)`, `.close()`.
- Produces: `tests/support/target.py` with the session fixture `target_runtime`, yielding `(rt, sim)`. `rt` is a `TargetClient` wrapping `hms.client.Client` with `invoke(instance_id, action_id, arguments) -> operation_id` (issues a namespace, prepares, invokes), `wait(operation_id, timeout_s=5) -> operation`, `invoke_error(instance_id, action_id, arguments) -> error_code` and `observe(instance_id, property) -> observation`.
- Produces: installation kind `compact-target-sim` in `hms/installations.py`. It reuses `CompactSimulation` in `hms/endpoint_binding.py` and `--endpoint-fd`; observations carry evidence kind `simulation` and source `target-binary-sim`.

- [ ] **Step 1: Failing test**

```python
# tests/test_target_sim.py
import pytest
pytestmark = pytest.mark.target

def test_target_sim_executes_scenarios(target_runtime):
    rt, sim = target_runtime   # daemon + simavr running hms_finite_328p.elf
    op = rt.invoke("sim:uno", "pwm_set", {"channel": "D3", "duty": 128})
    assert rt.wait(op)["state"] == "completed"
    assert sim.pwm(timer=2, channel="B") == 128      # read from the simulated MCU, not the host
    assert rt.observe("sim:uno", "pwm_d3")["evidenceKind"] == "simulation"

def test_refuses_timer1_pwm_on_target(target_runtime):
    rt, _ = target_runtime
    assert rt.invoke_error("sim:uno", "pwm_set", {"channel": "D9", "duty": 1}) == "UNSUPPORTED_CAPABILITY"
```

- [ ] **Step 2:** Confirm failure (`simavr_host` missing).
- [ ] **Step 3:** Implement `simavr_host.c` on libsimavr: load the ELF, attach the UART IRQs to the socket, register IRQ hooks for the ports and Timer2 compare registers, and load and save the EEPROM file.
- [ ] **Step 4:** Implement the `target_runtime` fixture and the installation kind. Confirm both tests pass.
- [ ] **Step 5:** Run the framed-process endpoint scenarios driven by `scripts/check_endpoint_integration.py` and `scripts/check_endpoint_scenarios.py` (13 at the last recorded run) against the target binary. Expected: every reply frame matches the host-native result byte for byte.
- [ ] **Step 6:** Commit — `test: execute the AVR firmware in simavr through the full host stack`.

### Task 4: Reset, power loss and timing at the target

- [ ] **Step 1: Reset sweep.** Start an operation, call `power_cycle()` at each of 200 evenly spaced cycle counts between frame receipt and reply, reconnect, and query. Assert every case ends in exactly one of: not started (provably no pin change), completed with a receipt, or `outcome_unknown`. Assert no case shows a second pin transition. This pins Review Focus item 4 at T2.
- [ ] **Step 2: Boot-epoch persistence.** After each power cycle the endpoint session identity differs from every earlier one and old-session frames are rejected. Run until the finite boot reservation bank is exhausted; assert the endpoint refuses to arm, not wraps.
- [ ] **Step 3: Stack high-water mark.** Fill SRAM with a pattern before start, run all scenarios, and read the untouched depth through the control socket. Assert measured use is at or below the static analysis bound recorded in `combined-stack-analysis.json`.
- [ ] **Step 4: UART overrun.** Send frames at the maximum 430-byte wire size back to back at 115,200 baud. Assert no receive overrun is missed: every dropped byte produces a counted framing error and a resynchronization, never a corrupted accepted frame.
- [ ] **Step 5:** Update `docs/evidence-matrix.md` rows MCU-01, LEASE-03 and WIRE-01 to T2 with the stated limits: simavr timing is cycle-counted but not electrically validated.
- [ ] **Step 6:** Commit.

### Task 5: Verification foundations used by every later phase

- [ ] **Step 1: Fuzz targets.** `protocol/fuzz/fuzz_frame.c` and `fuzz_endpoint.c` with libFuzzer (`clang -fsanitize=fuzzer,address,undefined`). Seed from `protocol/endpoint/vectors.json`. `scripts/ci.py nightly` runs each for 30 minutes and keeps the corpus.
- [ ] **Step 2: Property tests** with hypothesis for `hms.contracts.parse_invoke`, `hms.pat_contracts.parse_pat`, `hms.procedures.parse_procedure` and `hms.endpoint_wire` encode/decode round trips. Each property: parse never raises anything but the module's declared error type; accepted input re-canonicalizes to the same digest.
- [ ] **Step 3: Differential test** of the Python and C frame codecs on 100,000 random frames.
- [ ] **Step 4: Deterministic simulation harness** at `tests/dst/`. `Runtime` already accepts injected `wall_clock_ms` and `monotonic_ms` and exposes `tick()`. The harness runs one runtime single-threaded under a seeded scheduler that interleaves `request`, adapter `tick`, clock steps and process kills at the crash points the existing crash drivers use. Invariants checked after every step: at most one live claim per resource; no operation leaves a terminal state; a replayed key returns the same operation; an operation that reached `dispatching` never returns to `accepted`. Nightly: 1,000 seeds; a failing seed is written to the receipt.
- [ ] **Step 5: First formal model.** `formal/journal.tla` covering replay namespaces, fencing floors and owner-epoch recovery, model-checked with TLC for two principals, two resources and one crash. The invariants are the same four as in Step 4.
- [ ] **Step 6:** Commit.

**Phase 1 exit gate (M1):** `scripts/ci.py target` passes; the reset sweep shows zero duplicate effects across 200 cut points; fuzzers run 30 minutes with no finding; the evidence matrix shows T2 rows.

---

## 10. Phases 2–12 (task level)

Each phase lists its tasks with files, interfaces, tests and exit evidence. A step-level plan is written when the phase starts.

### Phase 2: First physical effect (M2, T3)

**Needs hardware** (section 13). **Research gate:** R2.

| Task | Files | Interfaces and tests | Exit evidence |
|---|---|---|---|
| 2.1 Serial transport | Create `hms/endpoint_serial.py`; modify `hms/installations.py`, `hms/cli.py` | `SerialEndpointStream(path, baud=115200)` using stdlib `termios` (no new dependency), exclusive lock (`TIOCEXCL`), DTR handling that does not reset the board on open. Installation kind `compact-serial`; CLI flag `--endpoint-serial ADAPTER=/dev/ttyACM0`. Observations carry `controller_reported` | Unit tests against a pty |
| 2.2 Lossy-link tests | `tests/test_serial_faults.py` | `test_serial_partial_and_corrupt_frames`: a pty proxy drops, splits, duplicates and flips bytes at seeded positions; every fault ends in a resynchronized link and either an exact reply or `outcome_unknown`; no corrupted frame is accepted (Review Focus 3) | 10,000 seeded faults, zero accepted corruption |
| 2.3 Flash and identify | `scripts/flash.py`, `firmware/TOOLCHAIN.md` | `flash.py --port … --elf …` via avrdude; verifies the ELF digest against the endpoint's reported capability digest after boot | Flash log retained |
| 2.4 Bench fixture | `bench/uno-loopback/README.md` (wiring), `tests/hil/test_uno_loopback.py`, `tools/bench/capture.py` (sigrok) | Wiring: D3 PWM → RC filter → A0; D4 → D7; D13 LED. Tests marked `hil`: PWM duty measured by ADC within a tolerance set before measuring; GPIO out read back on a separate pin; a logic analyzer independently times PWM edges; USB port power cut with `uhubctl` mid-operation (Review Focus 4 at T3) | Logic-analyzer captures stored through `scripts/evidence.py`; matrix rows OBS-02, OP-04, CANCEL-03 at T3 |
| 2.5 Timing measurement | `scripts/benchmark_hil.py`, `docs/local-performance.md` | p50/p95/p99/max for admission, dispatch, endpoint acknowledgement and measured pin change, 10,000 samples, budgets written before measuring | Raw samples published |

**Exit gate (M2):** `hctl invoke` changes a pin on a real Uno, and a second instrument confirms it; power-cut tests show no duplicate effect.

### Phase 3: PAT on the public surface and the learning loop (M3)

**Research gate:** R3. Runs in parallel with Phases 1–2.

| Task | Files | Interfaces and tests |
|---|---|---|
| 3.1 Mount PAT | Create `hms/pat_service.py`; modify `hms/runtime.py` (`_request`), `schemas/local-api.schema.json`, `hms/api_contracts.py`, `hms/cli.py`, `hms/mcp.py` | `PatService(runtime)` owns one `PatCatalog`, one `PatExecutionStore` and one `RegistryPatBindings`. Method mapping: `pat_publish` → `PatCatalog.publish(context, artifact)`; `pat_evaluate` → `.evaluate(context, artifact_digest, evaluator_id, run_id)`; `pat_transition` → `.transition(context, artifact_digest, expected_revision=, target=)`; `pat_describe` → `.describe`; `pat_list` → `.snapshot`; `pat_events` → `.events`; `pat_run`/`pat_status`/`pat_cancel`/`pat_resume` → `PatExecutionStore.run/status/cancel/resume`. Tests: each method through CLI, socket and MCP; replay with the original key adds no effect; `pat_transition` needs the `pat:promote` grant, separate from `invoke` |
| 3.2 Intent handoff | Create `hms/intent_contracts.py`, `hms/intent_store.py` (adopted from `artifacts/implementation/prompt-intent-handoff/intent_handoff/`); modify the same surface files | Methods `intent_put`, `intent_get`, `proposal_put` with the adopted request shapes (`hms.application-intent/0.1`, `hms.application-proposal/0.1`). Replace the candidate's private `require`/`closed` helpers with `hms.checks`. Its 22 tests move to `tests/test_intent_store.py` |
| 3.3 Qualification service | Create `hms/qualification_service.py`; modify surface files | `qualification_submit(artifactDigest, parameters, bindings)` → attempt id; `qualification_status(attemptId)`. Wraps `hms_qualification.supervisor`. **Case budget is derived from the declared parameter domain, not fixed:** the current 32-case ceiling cannot cover the 35 cases an ordinary singleton integer parameter needs. The budget becomes `cases(domain) ≤ deployment limit`, and a domain needing more cases than the limit is refused with `QUALIFICATION_DOMAIN_TOO_LARGE` |
| 3.4 Deterministic router | Modify `hms/pat_execution.py`, `docs/pat-execution.md` | `pat_run` with a trigger selects exactly one eligible PAT or returns a typed non-selection: `NO_ELIGIBLE_PAT` (go to the agent), `AMBIGUOUS` (go to the agent), `EVIDENCE_UNAVAILABLE` (restore and retry, not novelty), `PRIOR_OUTCOME_UNRESOLVED` (reconcile first). Tests cover each branch and prove an unavailable candidate is never dropped to make another look unique |
| 3.5 Trace export for learning | Create `hms/trace_export.py`; method `pat_trace` | Returns the complete trace for one instance: proposal, admitted intent, operation states, observations, overrides, unresolved effects. Read-only; the agent uses it to propose a revision through `proposal_put` |
| 3.6 Reuse metrics | Create `hms/pat_metrics.py`; method `pat_metrics` | Counters per application: runs, deterministic selections, escalations by reason, false reuse (a selected run whose outcome check failed), unknown outcomes |
| 3.7 Agent-side synthesizer | In the Harness (Phase 9a): a `hardware-app-builder` skill | Reads `intent_get` and `discover`/`describe`, writes a `hms.pat/0.1` candidate, calls `proposal_put`, `qualification_submit`, `pat_transition`. The runtime stays model-free |

**Exit gate (M3), measured on the T2 target:** a natural-language request produces a qualified, promoted PAT; ten repeat triggers run with **zero planning model requests** (asserted from the Harness session record); a deliberately out-of-domain trigger escalates; a withdrawn-evidence trigger refuses without escalating.

### Phase 4: Standing applications (M4, T4)

**Research gate:** R4. **Decisions:** D5, D10.

| Task | Files | Interfaces and tests |
|---|---|---|
| 4.1 Adopt the standing host | Create `hms/standing_contracts.py`, `standing_wire.py`, `standing_store.py`, `standing_pat.py`, `standing_capacity.py`, `standing_endpoint.py` from `artifacts/implementation/standing-host-selection-reuse/project/hms/`; mount six `standing_*` methods | Host API: `StandingHost.prepare/open/status/mutate/collect/reconcile/revoke`. Wire opcodes: DESCRIBE 0x01, BIND 0x10, REVOKE 0x12, OPEN 0x40, START 0x41, RENEW 0x42, STATUS 0x43, ACK 0x44, SUSPEND 0x45, RESUME 0x46, STOP 0x47, RETIRE 0x48. Bring the 20 host cases, 13 owner-death cuts and 18 boundary controls into `tests/` |
| 4.2 Resolve the capacity failure by measurement | `tests/test_standing_capacity.py`, `docs/decisions/standing-capacity.md` | The 128-record scenario misses its 30 s bound at 110 records. Profile it with `cProfile` and per-transaction fsync counts. Per D6, write the decision: either batch settlements into one transaction per collection (a design change that keeps commit-before-ACK), or restate the bound from a measured requirement. No fourth blind attempt |
| 4.3 Standing firmware on the ATmega2560 | `firmware/apps/standing_2560.c`, `firmware/kernels/{hysteresis,threshold,timer,edge,pi}.c` from the `standing-endpoint-phase-kernels` source | Build with the 2560 toolchain file; size gate at 80% of 253,952 bytes. Run the 14 standing cases and the six differential traces natively, then in simavr (`--mcu atmega2560`) |
| 4.4 Kernel catalog and lowering | Modify `hms/pat_compiler.py`; create `hms/standing_kernels.py`; spec section in `docs/prompt-to-pat.md` | New profile `hms.pat.standing-kernel/0.1`: a PAT names one installed kernel and typed parameters (inputs, outputs, limits, lease, loss policy). The compiler refuses any kernel or parameter the endpoint's DESCRIBE does not advertise |
| 4.5 Sensor drivers | `firmware/drivers/ds18b20.c`, `ntc_adc.c` | Bounded start/poll/collect with explicit timeout, per `spec/12`. Tested in simavr with a modelled 1-Wire device |
| 4.6 The enclosure application | `bench/enclosure/README.md`, `tests/hil/test_enclosure.py` | Fan on a MOSFET, temperature sensor, heat source. The whole flow from M3 runs against it. Faults injected: sensor unplugged, fan stalled, hub killed (controller keeps running under its lease, then applies its loss policy), manual override |
| 4.7 Cortex-M port | `firmware/cmake/arm-rp2040.cmake` or Uno R4, `protocol/platform/rp2040_*.c` | Same endpoint sources; platform layer only. T2 in QEMU or Renode per R1, then T3 |

**Exit gate (M4):** the enclosure holds its temperature band for 24 hours with no model call after promotion; pulling the hub's power leaves the controller in its declared state, confirmed by an independent logger.

### Phase 5: Adapter SDK, isolation and the binding ladder (M5)

**Research gate:** R5, one sub-lane per adapter. **Decisions:** D8, D9, D12.

| Task | Files | Interfaces and tests |
|---|---|---|
| 5.1 Adapter protocol | Create `hms/adapter_api.py` | `class Adapter(Protocol)` with the methods the runtime already calls: `validate_admission(intent, binding, resources)`, `refresh(*, force=False)`, `tick()`, `result(operation_id)`, `close()`; plus `describe_installation() -> dict`. `LocalSimulation`, `CompactSimulation` and `IoRouteAdapter` are declared to implement it; no behaviour change |
| 5.2 Out-of-process workers | Create `hms/adapter_host.py` (supervisor side), `hms/adapter_worker.py` (worker side) | Protocol `hms.adapter/0.1`: canonical-JSON frames over a socketpair. Messages: `hello`, `validate`, `dispatch`, `query`, `cancel`, `observe`, `presence`, `heartbeat`. The host bounds the queue (64), kills a worker that misses three heartbeats, and marks its in-flight operations `outcome_unknown`. A stalled worker never blocks another route. Tests: SIGSTOP a worker and show an unrelated device still completes work |
| 5.3 Driver lifecycle | Adopt `io-lifecycle-settlement`; methods `driver_change`, `driver_status` | A change computes the affected dependency set, refuses while it is busy, holds the claims through settlement, and publishes a new generation. Needs the `configure` grant |
| 5.4 Conformance kit | Create package `hms_conformance/` | `python -m hms_conformance --installation <file> --twin <cmd>` runs every applicable ID from `docs/conformance-plan.md` (AUTH, DESC, OBS, LEASE, OP, CANCEL, REG, WIRE, STREAM) against an adapter and writes a result table with the six allowed statuses. An adapter is "supported" for exactly the rows that pass |
| 5.5 Adapter layout | `adapters/<name>/{adapter.py, installation.json, types/*.json, twin/, tests/, uv.lock, GUARANTEES.md}` | `GUARANTEES.md` states what each native acknowledgement proves and what is unavailable. Each adapter has its own locked environment |
| 5.6 Rung 1 adapters | `adapters/firmata`, `scpi`, `modbus`, `mqtt`, `opcua`, `ros2_action` | See the table below |
| 5.7 Rung 2 bridge | `adapters/gui_bridge` | Drives a vendor GUI through an accessibility or screenshot API. Every observation is `estimate`; every action reports weak acknowledgement. Twin: a small test GUI |
| 5.8 Rung 3 retrofit axis | `adapters/retrofit_axis` | One stepper with encoder and limits on the serial endpoint. Capability `org.bud.positioning.axis`. Twin: simavr plus a modelled lead screw with backlash |
| 5.9 Graduation | `hms/binding_history.py` (extends `reg_binding_history`), `docs/binding-ladder.md` | Re-binding an action from one rung to another creates a new binding generation, invalidates PATs qualified on the old one, and requires re-qualification. The agent-facing action id does not change |

| Adapter | Software twin (T1) | First real target (T3) |
|---|---|---|
| Firmata | simavr running StandardFirmata | Any stock Arduino, no custom firmware |
| SCPI over TCP/USBTMC | Scripted instrument server implementing the parser states read in R5 | A bench multimeter or power supply |
| Modbus TCP/RTU | pymodbus simulator | A low-cost relay or sensor module |
| MQTT / Home Assistant | Mosquitto and Home Assistant demo devices in Docker | A smart plug and a temperature sensor |
| OPC UA | asyncua server with a method and a program | OpenPLC or a PLC trainer |
| ROS 2 action | Docker ROS 2 with a mock action server and ros2_control mock hardware | A small arm (LeRobot SO-101 class) |

**Exit gate (M5):** three rung-1 adapters pass the kit against twins; one stalls without affecting the others; the result tables are published.

### Phase 6: Data plane and streams

**Research gate:** R6.

| Task | Files | Interfaces and tests |
|---|---|---|
| 6.1 `watch` | Modify `hms/runtime.py`, schema; create `hms/watch.py` | `watch(instanceId, after, limit, waitMs)` → events with cursor, producer epoch, sequence and explicit gap markers. A cursor from an old epoch returns `CURSOR_EPOCH_CHANGED` and requires a fresh observation. Covers STREAM-01 |
| 6.2 Artifact store | Create `hms/data_store.py` | Content-addressed, quota per deployment, atomic publication (write, fsync, rename), retention policy. An interrupted upload is never visible as complete. Covers ART-01 |
| 6.3 Data references | Schema `dataRef`; methods `dataref_describe`, `dataref_read` | Fields: dtype, shape, layout, units, frame, capture time and clock, calibration revision, sha256, access scope, expiry. A missing frame is a gap, never the previous frame |
| 6.4 Shared-memory ring | Create `hms/shm_ring.py`, `protocol/shm/ring.h` | Versioned header, sequence counter, single writer, read-only consumer mappings, overwrite-oldest with a loss counter. Commands never travel through it |
| 6.5 Camera adapter | `adapters/uvc_camera` | Capture is an operation with declared effects (exposure, illumination trigger). Frames go to the ring and the artifact store. Twin: a file-backed synthetic camera with injectable stalls and stale frames |
| 6.6 Harness streams | Phase 9c | Live display uses `ctx.streams`; every model-visible image enters the session log |

**Exit gate:** a 30 fps camera stream runs alongside 100 Hz observations with no control-path latency increase beyond the budget set beforehand; an injected stall produces a visible gap.

### Phase 7: Authority, security and the stop path

**Research gate:** R7, R11.

| Task | Files | Interfaces and tests |
|---|---|---|
| 7.1 Per-agent delegation | Create `hms/delegation.py`; methods `delegation_issue`, `delegation_revoke` | The authority mints a token bound to principal, session, action and resource scopes, limits and expiry, as an HMAC caveat chain it verifies itself. Holders can attenuate but never widen. `test_delegation_scopes_are_independent`: two tokens under one UID cannot use each other's scopes (Review Focus 5). Tokens never appear in model-visible output |
| 7.2 Remote transport | Create `hms/remote.py`; CLI `serve --listen` | The same canonical-JSON frames over TLS 1.3 with mutual authentication (stdlib `ssl`). The principal comes from the client certificate plus a delegation token. Tests: wrong CA, expired certificate, replayed frame, slow-loris |
| 7.3 MCP over HTTP | Extend `hms/mcp.py` | Streamable HTTP projection behind 7.2. Long work returns an operation handle; no MCP call is held open for an experiment |
| 7.4 Independent stop | Create `hms/stop_service.py`; method `stop` | A separate process and socket. It authenticates stop authority, resolves the commissioned stop procedure, and reaches the adapter without waiting on the journal writer lock. With the journal unavailable it executes with `degraded_audit` and buffers evidence. It carries no move or setpoint. Tests: stop succeeds while the authority database is locked; stop is refused without the `stop` grant |
| 7.5 Human approval | Methods `approval_request`, `approval_status` | An approval is bound to one request digest and granted by an authenticated user decision delivered through the host application. A model-supplied `confirmed: true` is rejected by schema |
| 7.6 Signed type bundles and enrollment | Create `hms/signing.py` (Ed25519; adds the pinned `cryptography` package, the one planned core-dependency exception, taken only after R7's decision record) | Enrollment binds a device or gateway key to a site and allowed types. An advertisement cannot replace an enrolled instance by reusing its name. Covers REG-02 |
| 7.7 Threat model | `docs/threat-model.md` | Trust boundaries per deployment profile; what serial CRC does not provide; what each security profile is unsuitable for |

**Exit gate:** matrix rows AUTH-01..03, LEASE-02 and CANCEL-01 pass over the remote transport; an external review of `docs/threat-model.md` is recorded.

### Phase 8: Hub, models and learned control (M7)

**Research gate:** R8, R9. Development hub: the second machine on the LAN (`bmh-worker`: Ryzen AI MAX+ 395, Radeon 8060S with 46 GB visible, XDNA NPU, 91 GB unified memory), which matches the unified-memory hub profile. NVIDIA-only tools stay on the workstation's RTX 3080. GB10 qualification follows when hardware is available.

| Task | Files | Interfaces and tests |
|---|---|---|
| 8.1 Hub job provider | Create package `hms_hub/` from `owned-hub-jobs`, `-recovery`, `-crash-harness`, `-writer-deferral`; methods `job_submit`, `job_status`, `job_cancel` | A compute job is an operation with claims on `gpu_memory_mb`, `cpu_cores`, `ram_mb`. Bring the five recovery groups, twelve owner-death checkpoints and three held-writer cases into `tests/` |
| 8.2 Models as resources | Type-bundle profile `hms.model/0.1`; `adapters/model_server` | A model is identified by weight digest, runtime, quantization and memory budget. Loading and unloading are managed operations. Admission refuses a job whose budget exceeds free GPU memory; it never relies on the allocator failing |
| 8.3 Perception stage in a PAT | Modify `hms/pat_compiler.py` | A step kind `pinned_inference` names a model digest, input data reference and output schema. It counts as model execution, not planning; `pat_metrics` reports the two separately |
| 8.4 Learned-control binding | `adapters/policy_server`, `docs/learned-control-profile.md` | A policy advertises embodiment, action convention, observation requirements, rate and age budgets. Each action chunk is admitted with a maximum observation age and an expiry; a late chunk is dropped and counted. A termination monitor independent of the model's "done" output decides completion |
| 8.5 Manipulator binding (rung 4) | `adapters/manipulator`, twin in MuJoCo with a LeRobot environment | Capability `org.bud.manipulation.press`, `.turn`, `.grasp_place`, each with a vision-verified postcondition. Observations are `estimate` unless a native sensor confirms. Policies (ACT, SmolVLA) run on the hub's GPU, not on the workstation |
| 8.6 Graduation demonstration | `tests/scenario/test_graduation.py` | The manipulator operates a knob in simulation; the trace yields a PAT; the action is re-bound to the retrofit axis (5.8) and re-qualified; the agent-facing call is unchanged |
| 8.7 Local agent on the hub | Phase 9 profile | A local model drives the same tools with the same delegation limits as a remote one. GPU saturation must not delay stop handling: measured in 8.8 |
| 8.8 Contention measurement | `scripts/benchmark_hub.py` | Controller service gaps, stop latency and admission p99 while the GPU runs at full load. Budgets set beforehand. Covers MCU-02 |

**Exit gate (M7):** a PAT with a perception stage runs on the hub; stop latency under GPU saturation stays within its budget; the graduation test passes.

### Phase 9: Bud-Meta-Harness production integration (continuous)

Work in a **fresh clone**; the three audited worktrees stay frozen.

| Stage | Packages | Content | Tests |
|---|---|---|---|
| 9a | `hardware`, `hardware-hms`, `tool-hardware`, `hardware-profile` rebased onto current Harness; new PAT, intent and qualification tools; `hardware-app-builder` skill | Tool schemas generated from `schemas/local-api.schema.json` by the existing `integration/harness/generate_schemas.py` | The 16 existing flows; keyless recorded sessions; the M3 zero-planning-call assertion |
| 9b | `hardware-jobs` | Process-local job view of a durable operation; restart rebuilds the view without resubmitting | Interrupted active-work recovery; outer admission-reply loss; in-flight framework cancellation |
| 9c | `hardware-streams`, `client-ui-hardware` | Live telemetry and video; operation cards built from persisted facts | UI replay tests |
| 9d | Delegation | One delegation token per session from Phase 7.1; a forked session gets history, not authority | AGENT-01, CANCEL-02 |
| 9e | Release | Promotion out of `experimental/` per the Harness package policy | Release acceptance and the shipped-profile session corpus |

### Phase 10: The three scenarios (M5, M6)

Each scenario runs first against twins with the full fault list in `spec/04-scenarios.md`, then on hardware.

| Scenario | T1 (twins) | T3/T4 (hardware) | Evidence required by the spec |
|---|---|---|---|
| Home ventilation | MQTT and Home Assistant twins: temperature, air quality, fan, window actuator | A room with a real sensor, fan and smart plug; cloud disconnected | Zero double execution on retry; old epoch rejected; stale telemetry refused; manual override shown |
| Microscope focus | Retrofit-axis twin with backlash, synthetic camera with focus model | The owner's microscope (details needed, section 13), or a bench focus fixture with a dial indicator and UVC camera | MICRO-01 … MICRO-08: repeatability and backlash distributions, slip detection, image-to-position pairing |
| Inspection cell | OPC UA PLC twin, conveyor model, camera inspection with a pinned model | A PLC trainer or small conveyor | Controller traces, cycle-time distributions, operator takeover, stale readback |

Add the second laboratory profile from the spec (liquid handler, plate transport, reader) at T1 using a SiLA 2 or PyLabRobot twin, to exercise material identity and irreversible dispenses (`spec/06`).

**Exit gates:** M5 when home and inspection pass at T1 with all listed faults; M6 when the microscope rows pass at T4.

### Phase 11: Scale, federation and performance (M8)

**Research gate:** R10. **Decision:** D11.

| Task | Content | Tests and budgets |
|---|---|---|
| 11.1 Performance protocol | `scripts/benchmark.py`, `docs/performance-protocol.md`: budgets written before measuring; p50/p95/p99/max; raw samples published | Per-method budgets for one site on the reference machine |
| 11.2 Journal throughput | Profile first. Options in order: prepared-statement and validation caching (already begun), group commit of independent admissions under one fsync, a WAL profile with a written durability analysis | Every option keeps the crash-window tests and the simulation-testing invariants green |
| 11.3 Large inventory | Indexed discovery with pagination; no per-device model tool | SCALE-01 at 10,000 and 100,000 instances with churn: bounded memory and page size |
| 11.4 Federation | Create `hms/federation.py`; protocol `hms.federation/0.1` | Sites exchange signed catalog summaries and scoped routing references. A site keeps authority over its devices and works offline. During a partition no remote writer takes ownership. Model `formal/federation.tla`; test with three sites and partitions |
| 11.5 Soak and chaos | `tests/soak/` | 72 hours, 50 simulated devices across five adapters, two real devices, random worker kills, link faults and hub restarts. Zero duplicate effects; every unknown outcome reconciled or reported |
| 11.6 Native core gate | Decision record | Taken only if 11.2 misses its budgets. A Rust journal and admission core behind the same contracts, differentially tested against the Python reference, which remains the executable specification |

### Phase 12: Standardization and release (M9)

| Task | Content |
|---|---|
| 12.1 Spec 0.2 freeze | Normative language pass over `spec/`; every MUST mapped to a conformance ID; stable vocabulary for capabilities, units and frames |
| 12.2 Public conformance suite | `hms_conformance` released with valid and invalid vectors for every normative operation |
| 12.3 Second implementation | A TypeScript client and an independent endpoint implementation (Rust, `no_std`) built from the spec alone, to prove the spec is sufficient. Interop tests in both directions |
| 12.4 WoT alignment | Type bundles validated as TD 1.1; Thing Model and binding templates finished |
| 12.5 MHS bridge | When R12 finds a public schema: a mapping document stating what is preserved, unavailable or augmented, then an adapter or projection. Until then, no claim |
| 12.6 Deployer documentation | Commissioning guide, threat model, the list of things HMS does not provide (no safety rating, no universal latency), per R11 |
| 12.7 Release | Versioned packages, signed artifacts, a public evidence matrix, governance and contribution policy |

---

## 11. Verification and testing strategy (cross-cutting)

**Layers.** Each layer catches what the one before it cannot.

| Layer | Tooling | Catches | Runs |
|---|---|---|---|
| Unit and contract | pytest; schema vectors | Logic and shape errors | Every commit |
| Property | hypothesis | Parser and canonicalization edge cases | Every commit |
| Differential | Python vs C codecs; Python vs second implementation | Divergent interpretations of the spec | Every commit |
| Process | Real daemon, CLI, MCP, C endpoint | Integration and framing | Every commit |
| Crash injection | Existing crash drivers; kill at each durable boundary | Lost or duplicated operations | Every commit |
| Deterministic simulation | `tests/dst/`, seeded | Rare interleavings | Nightly, 1,000 seeds |
| Fuzzing | libFuzzer on C; hypothesis on Python | Memory errors, parser crashes | Nightly, 30 min per target |
| Sanitizers | ASan, UBSan on all native code; TSan on `simavr_host` and native helpers | Undefined behaviour, races | Every commit |
| Formal | TLA+ and TLC: journal, standing lease, owner handoff, federation | Design-level protocol errors | On change to a modelled protocol |
| Target simulation | simavr, QEMU | Real-binary behaviour, resets, stack | Every commit (`target` tier) |
| Hardware in the loop | Bench runner with devices attached | Electrical and timing reality | On merge to main; nightly |
| Scenario | Twins, then hardware | End-to-end semantics under faults | Per phase gate |
| Soak | 72-hour runs | Leaks, drift, rare faults | Per release |
| Mutation | mutmut on `journal.py`, `contracts.py`, `registry.py` | Tests that pass without checking anything | Per release |

**Fault injection matrix.** Every adapter and transport is tested against: drop, duplicate, reorder, delay, split, corrupt; peer crash before and after each durable boundary; clock step backwards and drift; storage full and fsync failure; worker stall; power cut; manual intervention. The expected result for each is one of three: provably not dispatched, reconciled receipt, or explicit unknown.

**Coverage.** Branch coverage is reported per module. Gates: at least 90% for `journal.py`, `registry.py`, `contracts.py`, `endpoint_wire.py` and the firmware endpoint; no module at zero.

**Performance.** Budgets are written before measuring and are per binding, never universal. A maximum observed latency is never called a guarantee.

**The evidence matrix** (`docs/evidence-matrix.md`) is the single status view. A row changes only with a linked test or receipt.

## 12. Risks and stop rules

| Risk | Signal | Response |
|---|---|---|
| Optimization loops without delivery | Three failed attempts at one limit | D6: written decision before any further attempt |
| T2 results mistaken for physical truth | A simavr result quoted without its tier | Tier label is mandatory in the matrix; R1 documents what simavr does not model |
| Hardware never arrives | Phase 2 blocked for two weeks | Continue Phases 3, 5, 7 at T1/T2; order the minimal kit first (section 13) |
| Adapter breadth without depth | Many adapters, none past T1 | No more than two adapters in progress until one reaches T3 |
| The agent learns unsafe reuse | False-reuse counter above zero | The PAT is suspended automatically; the trace goes to review; the applicability rule is tightened and re-qualified |
| Scope growth from "universal" | A device class is claimed without a conformance table | Support is only what a published kit result shows |
| MHS publishes an incompatible standard | R12 finds a public schema | 12.5 bridge; the semantic kernel does not depend on MHS |
| Safety expectations exceed what software can give | A deployer asks for a safety rating | `docs/threat-model.md` and the deployer guide state the limits; protection stays in the installation |
| Evidence store deletion breaks audits | A request to free disk space | Ingest and verify first; delete only with the owner's approval |

## 13. Inputs needed from the owner

None of these blocks Phases 0, 1 or 3.

1. **Minimal bench kit (unblocks Phase 2):** Arduino Uno R3, Arduino Mega 2560, an 8-channel USB logic analyzer (fx2lafw-compatible), a USB hub with per-port power switching, breadboard, resistors and capacitors for the loopback.
2. **Enclosure kit (Phase 4):** 5 V fan with MOSFET module, DS18B20 sensor, a small heat source, an independent temperature logger.
3. **Second target (Phase 4.7):** Raspberry Pi Pico or Arduino Uno R4.
4. **Microscope details (Phase 10):** make and model, which knobs, travel and torque, whether a camera is fitted. Without these the scenario runs on a bench focus fixture instead.
5. **Hub hardware (Phase 8):** whether a GB10/DGX Spark will be available, and when.
6. **Approval to deduplicate `artifacts/`** after Phase 0 Task 6 verifies the ingest.
7. **A git remote** for CI, or confirmation that CI stays local.

## 14. Requirement traceability

| Requirement (from `PROGRESS.md`) | Phases | Closing evidence |
|---|---|---|
| 1, 7. Extensive research, read in full | R track | Decision records R1–R13 with reading receipts |
| 2. Universal protocol, runtime, tool manager, registry, fast execution | 5, 6, 7, 11 | Conformance tables; performance report; federation tests |
| 3. Microscope knob devices | 5.8, 10 | MICRO-01 … MICRO-08 at T4 |
| 4. Broad processors; on-device and hub agents | 1, 2, 4.7, 8 | Support matrix: ATmega328P, ATmega2560, one Cortex-M, x86 hub, GB10 when available |
| 5. Physical-AI architectures and critique | R8, 8 | Learned-control binding and manipulator adapter with tests |
| 6. Foundational tool analogous to bash | 2, 3, 5, 9 | `hctl` and tools operating real devices across three protocol families |
| 8. Evidence-derived standard | 12 | Spec 0.2, public suite, second implementation |
| 9. Arduino dynamic control | 1, 2, 4 | M2 and M4 |
| 10. Home, scientific and manufacturing scenarios | 10 | The three scenario gates |
| Added: prompt-to-PAT learning and deterministic reuse | 3, 4, 9a | M3 and M4 with zero planning calls on repeat |
| Added: device I/O, drivers and hub control | 5.3, 6, 8 | Lifecycle, stream and hub-job tests; contention measurement |

## 15. Self-review record

- **Spec coverage:** every row of the requirement audit maps to a phase (section 14). Every conformance ID has an owning phase: AUTH/LEASE/REG in 7, DESC/OBS/OP/CANCEL in 1–2 and 5.4, MCU in 1, 2 and 8.8, WIRE in 1–2, STREAM/ART in 6, PLAN in 3 and 10, AGENT in 9, SCALE in 11, MICRO in 10.
- **Known thin spots, stated honestly:** Phases 2–12 are at task level by design and need their own step-level plans. Sizing figures are estimates. Budgets for timing and capacity are deliberately not given numbers here, because the project's rule is to set them from the selected device and procedure before measuring.
- **Type consistency:** method names in section 4 match the phase tables. Adopted class and method names (`PatCatalog`, `PatExecutionStore`, `StandingHost`, `IntentStore`, opcodes) were read from the source on 2026-11-13.
- **Review Focus:** each of the five items names the task and test that pins it.
