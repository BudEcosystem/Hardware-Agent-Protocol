# Independent endpoint code review

This receipt covers the original HMS C endpoint and byte-stream link, the host endpoint decoder, and the selected integration-checker changes. The exact reviewed copies are under `snapshot/`; `source-pins.json` pins every copy. The review did not edit production files.

Run the retained native probes from any directory:

```sh
python3 artifacts/verification/endpoint-code-review/run_review.py
```

The runner verifies its retained inputs, compiles the original endpoint, link, framing code and synthetic fixture with address and undefined-behavior sanitizers, runs 16 bounded cases, and retains exact commands, compiler identification, stdout/stderr and binary hashes in `probe-run.json`. It executes no acquired repository or physical adapter. The native source snapshot and deliberately adversarial callbacks are distinct from an installed physical driver.

The independent Python rerun is recorded in `python-run.json`: 18 existing packet tests, including a formerly verified physical completion that is later disputed. A `DISPUTED` receipt remains typed evidence of a dispute; it is not verified success. Cross-revision continuity, authenticated routing and durable host recovery remain outside this one-packet decoder.

`endpoint-code-review.json` records findings, resolutions, exact coverage and limitations. The native cases exercise mode changes, guard/callback cutoff crossings, post-callback clock loss, unknown-to-failed clock reasons, same-report and later disputed release, counter exhaustion, transmit backpressure, zero primitive IDs, and absolute receive assembly expiry. Receive expiry resets only partial framing state. The default 1000 ms receive budget is synthetic and requires platform qualification.

The reader inspected all of `endpoint.c`, `endpoint.h`, `link.c` and `link.h`, and reread every changed portion before pinning this final snapshot. No outstanding concrete implementation finding remains within that scope. This does not establish hardware fit, service deadlines, independent stop, qualified clocks/NVM, durable execution, complete state-space correctness, or a live-device integration. A driver still has to enforce the provided immutable cutoffs at actual I/O boundaries; a post-callback check cannot undo a physical effect.
