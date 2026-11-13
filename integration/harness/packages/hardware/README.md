---
description: "Typed service definition for independently authenticated hardware providers."
kind: "package-reference"
---

# @budmh/experimental-hardware

English | [中文](README.zh.md)

## Summary

Typed service definition for independently authenticated hardware providers.

## Use this package

Consumers inject `hardware` and call `request(method, params, { agent, signal })`. The provider owns authentication and response validation. Session identity supplies attribution and existing file policy only.

## Understand the implementation

The reply distinguishes a checked result from an unconfirmed error code. Accepted operations may continue after the caller stops waiting. Retain the original invoke envelope and inspect durable operation state before deciding what to do next.

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
