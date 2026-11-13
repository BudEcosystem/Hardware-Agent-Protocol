---
description: "Native and PTC tools for HMS simulation discovery, observations and durable operations."
kind: "package-reference"
---

# @budmh/experimental-tool-hardware

English | [中文](README.zh.md)

## Summary

Native and PTC tools for HMS simulation discovery, observations and durable operations.

## Use this package

Mount the tools service and a hardware provider. Nine `hardware_*` tools expose discover, describe, observe, namespace, prepare, invoke, operation, events, and cancel. Prepare returns an immutable request without admitting it; invoke takes that complete request. Do not rebuild a request after uncertain delivery.

## Understand the implementation

Canonical JSON contains `ok` and either the full checked `result` or a typed `error` with unconfirmed outcome. The `attribution` object carries Session and tool-call IDs; HMS never receives those as authority. Registration is effect-scoped and unload removes every tool. Native and PTC results use the same values.

## Model Experience

### Hardware tool output

#### What the model sees

Through the hardware tools, the model receives call-specific canonical results, evidence strength, and attribution. This package never upgrades simulation evidence into a verified physical effect.

#### Token effect

Tool schemas are conditional on composition; transport limits bound result size. Native results and PTC dispatch records remain in the Session.

#### KV Cache effect

Results append to existing tool history. Composition or tool-schema changes can alter request prefixes; provider cache availability is outside this package.

## Known Limitations and Deferred Work

Local Linux, same-UID simulation only: no per-agent authentication, physical hardware, HTTP, or remote transport. Starting Python for each call has measurable cost; no latency guarantee applies.
