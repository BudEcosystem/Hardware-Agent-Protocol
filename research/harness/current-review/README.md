# Current Harness source review

Read-only review on 2026-11-06 of `/home/bud/Desktop/bud/Bud-Meta-Harness` at clean commit `1f0762afd0ac9cf0a1a2e3ddb0861c0e3f7aaa44`. The checkout advanced from `d338750966ab11c0bb149e3b4914e2851f63e84f` during review; final snapshots were extracted from pinned Git commit blobs. The [manifest](manifest.json) records exact SHA-256 hashes, byte counts, line counts and reading ranges. No Harness code, configuration or retained original audit files were changed. No Harness tests or builds were run.

All 22 source files from the [original manifest](../manifest.json) match the reviewed commit byte-for-byte. Their original full/partial reading coverage remains explicit; a hash comparison is not a new full reading. All additional credential, identity, package and PTC sources read before the checkout moved were verified byte-identical between review heads. The manifest lists all changed paths; those paths were not all read. The [reviewed adjacent API diff](changed-adjacent-apis.diff) extracts the attachment byte-stream framing helper used by the Session controller without changing the inspected tool or credential APIs. The new helper and its tests were read in full; the other three affected files were reviewed through their complete diffs only.

The additional snapshots cover current instructions, credential and authorization service definitions, identity, package naming/composition, the PTC invocation implementation, and relevant test patterns. Each snapshot retains the full file; the manifest distinguishes full reading from exact partial ranges. The source's instructions are evidence for future Harness work; copied instructions do not authorize changes to that repository.

Findings incorporated into [the integration design](../../../../docs/harness-integration.md):

- An Agent and Session establish local attribution, not an authenticated human or hardware principal. `AgentRegistry.withInitiator` explicitly rejects that inference. The anonymous user id serves telemetry; `ctx.authorization` obtains credentials and does not implement device ACLs.
- `CredentialProvider.resolve` and `readCredentialValue` resolve secrets per operation. `readRecord` and serialized `modifyRecord` support provider-owned grant records and refresh. Credential material stays out of model arguments, results and Session logs.
- A UID-authenticated Unix socket provides user-level authority. Session-scoped privileges require a separate trusted delegation mechanism; same-UID shell access can bypass a tool-only restriction.
- Initial packages belong under `packages/experimental/` with `@budmh/experimental-` names and an explicit profile patch. An optional browser package is `experimental-client-ui-hardware`; its promoted Client name would be `client-ui-hardware`.
- PTC inner calls keep distinct call ids under the common outer/root call, use the normal scheduler, return canonical values, and log content/metadata. Program exceptions carry error messages; machine-readable hardware outcomes belong in canonical domain results.
- A native/PTC feature needs real Loader composition, real runtime execution, persisted Session replay and independent ledger-effect checks. The retained tests are implementation templates, not HMS integration test results.

Recheck the checkout and current instructions before implementing the proposed packages. This receipt supports the documented design at the pinned commit and does not establish live device or end-to-end Harness operation.
