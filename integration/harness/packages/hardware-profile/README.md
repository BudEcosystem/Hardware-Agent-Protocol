---
description: "Explicit experimental profile layer for local HMS simulation."
kind: "package-bundle"
---

# @budmh/experimental-hardware-profile

English | [中文](README.zh.md)

## Summary

Explicit experimental profile layer for local HMS simulation.

## Use this package

Apply `cordis.patch.yml` after the base profile. Set `HMS_ROOT` and `HMS_SOCKET` to absolute paths before startup, or override the `hardware-hms` row. The layer mounts the native provider and tools; it does not launch or initialize HMS.

## Understand the implementation

Start the separate HMS simulation daemon explicitly. All participating processes under one POSIX UID share authority. The layer neither grants per-agent rights nor projects delegated device credentials.

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
