# Harness tools through the compact C simulator

This lane adds two integration tests on isolated Harness commit `335a82eb121ccefc4c4bee98fc523a76eb218c5c`, after the preserved `revalidation-335a82eb` overlay. Both tests passed, along with focused lint and all three aggregate build checks. No production package or existing test file changed. The previous overlay, 14-test receipt, source snapshots and build receipts remain unchanged.

The first test composes the opt-in hardware layer with the actual Loader and executes the real Node PTC runtime. Its program prepares, invokes, reads and deliberately replays three requests: fan level 25 percent, microscope position 42 um in its explicit frame, and inspection recipe 1 for `part:α`. The recorded nested PTC dispatches retain identical invocation arguments and typed simulation evidence. The second test executes native tools with a real Agent from AgentLoop and repeats those three scenarios across host SIGKILL. These tests call the tool/PTC executor directly; they do not add a model-generated SDK conversation.

The path is Harness native/PTC tools → managed checked Python client → private HMS Unix socket → durable host binding → original framed protocol → original native C scenario process. The C process is owned by a separate test launcher and survives each host death. The fixture uses its real monotonic clock, no test-control FD, no physical port, and no external service. The fixed manifest and executable match the existing native scenario build receipt. `runtime-fixture/` contains the exact frozen 32 HMS inputs, the additional manifest, and the pinned original C source/build inputs and binary.

The loss window is precise: the byte relay forwards one OP, receives a native queued/running receipt, holds it away from the host, and the launcher kills and reaps that host. The test verifies the host's durable command still contains the exact reserved payload/sequence with no receipt. Only the launcher's verified stale socket inode is removed. The new host opens the existing authority state while the same C process continues. Explicit replay through the native tool retains the same request and operation identity, and reconciliation queries the original endpoint receipt. The test observes one OP handoff total for that operation; recovery never emits another OP. This is loss of the endpoint admission reply at the host, not loss of the outer hctl admission response, which the native tool already received.

Independent evidence comes from the relay's exact request/response bytes, decoded native completion receipts, and comparison with the host's retained packet reservations. The six completed operations have values 25, 42, 1 in each test and sample ticks matching the model-visible host results. Native observation after recovery also retains the C acquisition tick. Inspection's value 1 is its synthetic counter. Fan and focus values are idempotent setpoints, so those values alone are not duplicate-effect counters; the one-OP frame observation and retained operation identity bound the duplication claim. The real-clock fixture offers no separate read-only dispatch/effect-counter channel. No SQLite simulated plant is created in either case.

`compact-tests.patch` adds only `hms-compact.spec.ts` and `compact-launcher.py`. Apply the preserved base overlay first, then this additive patch in a checkout at 335a82eb. The new sources are also copied under `packages/tool-hardware/tests/`. The Python launcher's ReplyGate is copied from the original HMS CLI restart test, retained as `original-cli-relay-test.py`; new control code never invokes an HMS action. It only arms the reply gate, crashes/restarts the owned host, reads retained SQLite evidence, or closes its processes.

The exact successful test command is retained in `verification/final-tests.command.json`. On this workstation it is reproducible through the owned command runner:

```sh
HMS_COMPACT_ROOT=/home/bud/Desktop/bud/hms/integration/harness/compact-endpoint/runtime-fixture \
HMS_COMPACT_CAPTURE=/tmp/hms-compact-fresh-capture.jsonl \
python3 integration/harness/compact-endpoint/run-command.py repeat-tests \
  node node_modules/vitest/vitest.mjs run \
  packages/experimental/tool-hardware/tests/hms-compact.spec.ts --reporter=verbose
```

Use a new capture pathname for each run; the test appends four records. The runner uses the existing isolated 335a82eb worktree, Node 24.22.1 and its owned dependency caches. Prior artifact builds remain applicable because all 31 existing package source files and their build configuration are unchanged. The new aggregate check includes the added TypeScript test. The C binary was reused from its exact successful build receipt; this lane does not claim another native compilation or sanitizer run.

`verification.json` records exact input/source/binary/patch hashes, commands, terminal results and limits. `final-capture.jsonl` contains one PTC record and three native fault records, including complete wire frames. Development failures are retained separately: an assertion initially used the wrong PTC event field, and a test-only TypeScript interface declaration plus formatting needed correction. No production defect was found. No separate independent review of the new tests is claimed.

All callers share one Unix UID's authority. Agent and Session identifiers are attribution only. All effect evidence is simulation and remains physically unverified. This lane does not qualify mechanical motion, real imaging, MCU timing, power-loss durability, physical stop behavior, remote transport, per-agent delegation, a published install, or the shipped recorded-Session corpus.

At the finish-time read-only check, the live Harness checkout was clean but had advanced externally to `a16267881e98cdac5e1edd7ab6ff5d1dae0a8ff2`. These tests and patches remain pinned to 335a82eb; the newer revision was not revalidated in this lane. No live source or checkout was modified.
