# BHMS developer documentation

This is the map of the BHMS (Bud HMS) developer documentation: where to start, which guide answers which question, and
where the reference and the specification are. BHMS is a JSON-RPC 2.0 protocol, in the shape of MCP, for AI agents,
programs and people that discover, observe and operate physical devices, with durable operations, leases, honest
evidence and a stop that never waits.

**Status.** Protocol version `2026-11-15` (v0.2; servers also serve `2026-11-13`, v0.1). The Python SDK, gateway, agent
bridges, conformance runner and TypeScript SDK implement v0.2 (with v0.1 compatibility); the C library for
microcontrollers speaks BHMS-Compact version 2 (unchanged in v0.2). All are tested against simulated devices and
host-built firmware. No physical device has been validated yet; every example here runs against simulations.

## Start here

| Page | Read it when you want to |
|---|---|
| [Quickstart](quickstart.md) | go from nothing to a device that Claude or an OpenAI model can operate, behind a gateway, in one sitting |
| [Concepts](concepts.md) | understand devices, effects and evidence, durable operations and unknown outcomes, leases and fencing, stop, programs, gateways, the compact binding and conformance profiles |

## Guides

| Guide | For |
|---|---|
| [Wrapping a real instrument](guides/wrap-an-instrument.md) | putting SCPI, Modbus TCP or OPC UA instruments behind BHMS honestly (a complete SCPI adapter; SimLab's adapters as references) |
| [Arduino and other microcontrollers](guides/arduino.md) | the C library, the Arduino sketch, the description sidecar and serving a board through a gateway (also without a board) |
| [The BHMS Arm](guides/bhms-arm.md) | a complete physical device: joints, tools, hazards, E-stop and stop, its firmware driven through a gateway |
| [Writing programs](guides/programs.md) | bounded step sequences validated before they run, registered by digest and offered to agents as tools |
| [Leases and safety](guides/leases-and-safety.md) | leases and fencing, lost replies and unknown outcomes, operator resolution, stop, verified effects, a hardware checklist |
| [Deploying a gateway](guides/gateway.md) | principals, scopes, narrowed bounds, `bhms gateway check-policy`, policy reload, TLS and state |
| [Designing descriptions agents understand](guides/descriptions.md) | names, units, bounds, effects and evidence that make a model pick the right action |
| [Connecting agents](guides/connecting-agents.md) | Claude and any MCP client (stdio, Streamable HTTP), OpenAI Responses and Chat Completions, testing agent loops offline |
| [TypeScript SDK](guides/typescript.md) | device servers and clients in TypeScript, with the Python tools |
| [Running conformance](guides/conformance.md) | generic reports for your server, profile claims, `--device-command` for other SDKs |

## Reference

Generated from the code by [`tools/gen_reference.py`](tools/gen_reference.py) and checked by the test suite, so they
cannot drift from the implementation:

| Reference | Contents |
|---|---|
| [CLI](reference/cli.md) | every `bhms` command, argument and option |
| [Error codes](reference/errors.md) | every BHMS code with its JSON-RPC number, retry class and meaning |
| [Agent tools](reference/agent-tools.md) | the eight tools exactly as a model receives them |
| [Gateway configuration](reference/gateway-config.md) | every key of the gateway TOML file and its default |
| [Python API](reference/python-api.md) | `bhms`, `bhms.client`, `bhms.testing`, `bhms.bridges`, `bhms.gateway` |
| [TypeScript API](reference/typescript-api.md) | `@bhms/sdk` |

## Elsewhere

- The specification: [`spec/bhms`](../../spec/bhms/README.md) (normative; the JSON Schema is the contract), its
  [changelog](../../spec/bhms/CHANGELOG.md) and the [conformance index](../../spec/bhms/14-conformance.md).
- [Migrating to this release](migration.md): the changes of the hardening round that can break existing code.
- [Performance](performance.md): measured latency, throughput and scale against the budgets, with the misses.
- SDK and library READMEs: [`sdk/typescript`](../../sdk/typescript/README.md), [`sdk/c`](../../sdk/c/README.md);
  SimLab, the simulated laboratory: [`simlab`](../../simlab/README.md); benchmarks: [`bench`](../../bench/README.md);
  runnable example configurations: [`examples/bhms`](../../examples/bhms/gateway.toml).

## How the examples are tested

Every page in this directory is executed by `sdk/python/tests/test_docs_examples.py`: each page runs top to bottom in a
fresh directory, against real servers, gateways, bridges and host-built firmware, and what an `output` block shows must
appear in what the command printed. The word after a code block's language says what it is:

| Marker | Meaning |
|---|---|
| `run` | executed (Python with the SDK's interpreter, shell with `bash -e -o pipefail`); `exit=N` expects that exit status, `background` leaves it running for the rest of the page |
| `file=<path>` | written to that file for later blocks |
| `output` | what the previous block printed (`...` stands for anything that varies, such as ids and timings) |
| `no-run` | deliberately not executed: installation, hardware, another program's configuration; the text says why |
| `slow` | executed only by the slow run (`python3 -m pytest -m slow`): full conformance claims |
| `requires=` | needs Node.js (`node`), a C toolchain (`cmake`) or an OpenAI key (`openai`, run only when `OPENAI_API_KEY` is set; nothing else can reach the network) |

Run them with `cd sdk/python && python3 -m pytest -q tests/test_docs_examples.py`. A block without a marker fails the
test, so nothing here is an untested fragment by accident.
