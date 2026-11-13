# Native Harness integration for local HMS simulation

This directory carries a reviewable overlay for Bud Meta Harness at commit `1f0762afd0ac9cf0a1a2e3ddb0861c0e3f7aaa44`. Development and tests ran in `/home/bud/Desktop/bud/hms-harness-1f0762af`; the adjacent live checkout was not edited. Nothing was published.

The live checkout has since advanced externally to `335a82eb121ccefc4c4bee98fc523a76eb218c5c`. A [read-only drift review](live-head-drift-review.json) found no direct HMS API break, but shared build inputs and SDK/CLI work-item composition changed. The tests below validate the original pin; a reconciled overlay, isolated tests and build checks are still required for the newer revision.

The four experimental Cordis packages provide `ctx.hardware`, an HMS provider, nine native/PTC `hardware_*` tools, and an explicit profile layer. HMS remains a separate daemon and durable operation owner. The provider uses Harness's managed subprocess and sandbox services to run the checked Python client once per request. The client authenticates a private Linux Unix socket using POSIX ownership and `SO_PEERCRED` and validates method-specific responses.

All callers under one Unix UID share authority. Session and tool-call identifiers appear only as result attribution; they are never HMS principals, credentials, or delegated authorization. This implementation operates only the local HMS simulator. It does not supply a physical device adapter, per-agent credentials, MCP, HTTP, or a remote execution world.

## Use the overlay

Use an isolated checkout at the pinned revision. `harness.patch` includes the package sources, tests, documentation, project references, four new lockfile importers, and generated dependency graph. Apply it only after checking the base:

```sh
git rev-parse HEAD
git apply --check /absolute/path/to/hms/integration/harness/harness.patch
git apply /absolute/path/to/hms/integration/harness/harness.patch
```

Use a supported Node version (verification used Node 24.22.1) and install the workspace dependencies in that isolated checkout. The retained package sources also appear under `packages/` for direct review. Start HMS separately from its source root:

```sh
mkdir -m 700 /tmp/hms-harness-example
python3 -m hms serve --state-dir /tmp/hms-harness-example/state --socket /tmp/hms-harness-example/control.sock --init-simulation
```

Apply `packages/experimental/hardware-profile/cordis.patch.yml` after a supported Harness base profile. Set `HMS_ROOT` to the absolute HMS source directory and `HMS_SOCKET` to the socket path before launching the normal `budmh` profile. The layer does not create or reset HMS state. On an existing daemon state directory, omit `--init-simulation`.

The provider's configurable defaults are a 5000 ms whole-call deadline, 1000 ms termination grace, and 131072 output bytes. The underlying HMS local transport still enforces its own smaller request/framing limits and deadline. Both subprocess and sandbox providers must operate in the same local Linux execution world as the socket.

## Invocation and failure rules

Allocate a replay namespace, prepare the intended action, and retain the returned complete request. Preparation is advisory and does not admit an operation. Invoke forwards that request unchanged; it never creates a replacement operation key, refreshes generations, or retries automatically. Inspect the returned operation ID for execution, cancellation, resource claims, and effect verification. Simulation completion retains `evidenceKind: simulation` and does not verify a physical effect.

An interrupted or malformed provider reply produces a closed error code with `outcome: unconfirmed`. Harness caller cancellation after a tool body starts instead uses a typed `HMS_OUTCOME_UNCONFIRMED` framework error; a late framework `ABORTED` retains an explicit uncertainty warning. `ABORTED_BEFORE_DISPATCH` remains distinct. Canceling the Harness call stops its client subprocess and waits for cleanup; it does not cancel an already accepted HMS operation. Use `hardware_cancel` explicitly when that is intended, then inspect durable state. An exact deliberate replay can recover an uncertain submission while the same retained replay namespace remains valid; reconstructing the request changes intent and is unsafe.

Native tools and PTC bindings declare a closed tagged response union with attribution and method-specific result schemas. `generate_schemas.py WORKTREE` derives the Harness-supported value-schema subset from `schemas/local-api.schema.json`. Numeric bounds, string patterns, cross-field correlations and semantic admission remain authoritative in the checked Python client and HMS. Open dynamic description/body fields remain explicit JSON or open objects.

## Verification and limits

`verification.json` records exact commands, outcomes, source hashes and remaining gaps; `verification/` contains raw logs. The final focused run passed 12 tests; all seven artifact-build stages and all three aggregate checks passed after an isolated offline dependency installation. The focused integration test starts an actual local daemon, composes the experimental profile rows through the real Loader, and exercises native tools, the actual Node PTC runtime, and an actual AgentLoop with a keyless scripted model. It persists a Session capture and proves reconstructed model history matches. It also covers all three simulated scenarios, immutable replay and changed-request conflicts, physical-verification rejection, explicit future-operation cancellation, and tool removal on disposal. Framework cancellation tests use a mocked drained provider to deterministically exercise the real tool registry; they do not prove physical stopping or accepted-operation transport-loss recovery. PTC performs actual preparation, invocation, replay and operation reads. This tested composition retains full nested JSON; other PTC logging plugins may project previews or locators. Session reconstruction here does not test a production persistence plugin or crash recovery.

`session-capture.json` is a raw test receipt, not a fixture admitted to Harness's shipped-profile recorded-session corpus. A normal `budmh` shipped-profile snapshot scenario, release/package-install checks, and the complete repository gate set are still needed before treating this overlay as release-ready. No UI package or visual review is included.

`native-call-timings.jsonl` records complete native tool execution durations on this shared development machine, including Python startup and schema checks. It is a diagnostic sample, not a benchmark or a latency guarantee. A persistent checked bridge or a native peer-credential transport would need separate lifecycle and security work.

Initial dependency commands in the development worktree disabled pnpm's automatic pre-run install while using an existing dependency cache. The cache was subsequently copied into independent worktree-owned storage, and an offline frozen install passed before retrying the broader build. This affects dependency installation only; it does not disable validation or tests. The setting is not included in the overlay. pnpm documents that [`verifyDepsBeforeRun`](https://github.com/pnpm/pnpm.io/blob/main/versioned_docs/version-10.x/settings.md#verifydepsbeforerun) can trigger installation before `run` or `exec`; the consulted coverage was that setting only.
