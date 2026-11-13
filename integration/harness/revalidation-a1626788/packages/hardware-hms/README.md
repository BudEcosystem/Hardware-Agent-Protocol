---
description: "Local Linux HMS simulation provider using the checked Python client."
kind: "package-reference"
---

# @budmh/experimental-hardware-hms

English | [中文](README.zh.md)

## Summary

Local Linux HMS simulation provider using the checked Python client.

## Use this package

Configure absolute `hmsRoot` and `socketPath`; optional `pythonExecutable`, `timeoutMs` (5000), `graceMs` (1000), and `maxOutputBytes` (131072) bound each call. Mount local subprocess, sandbox, and sandbox-policy providers in the same execution world. The HMS source tree must provide `hms.client.Client`.

## Understand the implementation

Every call snapshots its parameters before awaiting, launches one bounded Python client, and validates the returned carrier. The client authenticates the local socket and validates method-specific results. No automatic retry occurs. Cancellation and disposal terminate and await the child, while the HMS operation may continue. Errors expose closed codes and `outcome: unconfirmed`; schema failures after delivery use `INVALID_RESPONSE`.

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
