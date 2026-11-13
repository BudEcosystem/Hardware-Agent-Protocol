# Installed adapter support — Harness compatibility evidence

The unchanged experimental Harness overlay at `a16267881e98cdac5e1edd7ab6ff5d1dae0a8ff2` passed all sixteen tests against the updated HMS installed-support checks in one combined run. Four test files passed with no skips in 68.39 seconds. The [verification receipt](verification.json) pins the command, output, captures, thirty-two current HMS inputs and forty-four fixture files.

The HMS changes affect `runtime.py`, `registry.py`, `simulator.py` and `endpoint_binding.py`. The separate [289-test runtime receipt](root-runtime-verification.json) includes the new unsupported-admission, dispatch-recheck, replay and historical-reconciliation regressions. The Harness run checks compatibility of the existing native/PTC/AgentLoop and built SDK/profile scenarios; it does not separately inject every new unsupported-installation condition through a Harness tool.

Six compact C scenario executions retain exact OP frames and independently decoded completed receipts. Three native-tool cases kill the host after endpoint acceptance and recover by QUERY with no second OP; three cases use actual Node PTC. Fan/focus OP counts establish handoffs, while the inspection counter and all device state remain synthetic. The SDK cases retain one effect through settled-work replay/reopen and distinguish Harness work cancellation from explicit HMS cancellation.

The [a162 baseline](../revalidation-a1626788/verification.json), its failed-run archives and its package bytes are preserved. All thirty-eight overlay source inputs match that baseline. Its seven artifact-build stages and three aggregate checks are reused because the JavaScript/TypeScript, build and dependency inputs are unchanged. This lane ran no build or install. It additionally pins 14,406 existing built files before and after execution; these hashes establish stability during this run, not byte identity to hashes recorded at the earlier build time.

The original native binary and [C build receipt](endpoint-scenarios-build-receipt.json) are reused by exact executable/source hashes. No target binary, physical device, external service or model inference ran. The live adjacent Harness checkout was not modified, and commits later than the tested a162 base are not validated by this result.

An earlier a162 combined run returned `DEVICE_UNAVAILABLE`; its cause remains unresolved. This passing run does not explain that refusal or establish reliable readiness under every scheduling/load condition. The earlier read-only SQLite observer contention fix remains part of the unchanged test helper. Physical qualification, multi-adapter coexistence, outer admission-reply loss, in-flight framework cancellation after endpoint acceptance and release/shipped-profile acceptance remain unfinished.

The new lane's captured evidence is checked with:

```sh
python3 -B integration/harness/installed-support/check_captures.py
```

`prepare_fixture.py` creates the retained fixture and checks reuse inputs; `run_tests.py` refuses to overwrite existing captures. They describe this validation setup, not a general installation or deployment command.
