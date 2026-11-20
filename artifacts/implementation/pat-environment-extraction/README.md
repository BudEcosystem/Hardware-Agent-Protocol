# Staged static PAT environment extraction

This lane contains a proposed compiler change only. Live `hms/`, tests, schemas and runner were not edited. It does not install qualification services or expose PAT methods publicly.

`staged/hms/pat_compiler.py` adds:

```python
evaluation_environment(artifact, bindings, *, deployment, evidence_mode="simulation")
```

The detached result contains `patDigest`, `compilerDigest`, `evaluationEnvironment`, `environmentDigest` and sorted `dependencies`. The helper validates the artifact, exact role closure, descriptor/type/binding consistency, metadata and digest syntax; it checks whole declared parameter domains, units/frames and companion arguments, literals, and each primitive's maximum run bound. It never needs a selected parameter assignment, operation keys or time. `compile_pat` shares the static checks and environment construction, retains concrete parameter/applicability, key, timing, argument-schema and lowering checks, and still returns the same fields.

The helper is static. It does not establish applicability for any parameter assignment, authenticate caller descriptors against installed devices, sample freshness, authorize a user, qualify an artifact or admit an operation. Parameter applicability can be false or even unsatisfiable while the static environment remains extractable. Environment identity intentionally preserves the existing formula: endpoint session is retained in dependency rows and run binding identity but excluded from the evaluation environment; binding, calibration, control generation, driver, installation, metadata, deployment and compiler identity remain visible. The artifact digest is returned separately; environment identity alone is not artifact identity.

Compiler implementation identity is fixed at import. The real staged source digest differs from the baseline, so future integration invalidates qualifications through the existing compiler identity closure. The helper performs no filesystem, clock or database access after that boundary. Trusted descriptor hashes are not independent attestations, and the fixture driver/installation hashes are explicitly synthetic test identities.

The refactor preserves run-level validation ordering before descriptor checks. Within each step it moves the shared static domain/semantic checks before concrete argument-schema validation. A compound-invalid input can therefore have a different first refusal code; no refusal is intentionally weakened. Runtime authorization and admission remain outside this pure compiler.

## Evidence

`baseline/inputs.json` pins 40 copied original inputs, including the approved service plan and source review. `build_fixtures.py` generates complete detached fan/focus/inspection descriptors from the copied original `hms.demo` definitions and the existing PAT fixture; the exact resulting bytes are retained at `fixtures/families.json`. No existing integration test is imported or executed.

`attempts/01/` retains the exact 78 pure-test input copies, before/after hashes, output and receipt. Eighteen tests passed with zero failures/errors/skips/expected failures and unchanged inputs. The local import record contains only this lane's snapshots and does not contain `hms.runtime`. Tests cover all three families, malformed artifact/roles/descriptors/metadata/digests, strict deployment/evidence context, full domains despite narrowed applicability, unit/frame/literal/parameter companions, primitive limits, session exclusion, changed binding/driver/installation/compiler context, detached outputs and deterministic ordering. Purity guards reject lowerer calls, parameter sampling, file reads, clocks and database opening during extraction.

Compatibility uses the actual copied baseline `compile_pat`, not a reimplemented formula. Six positive fan/focus/inspection lowerings compare complete outputs with only the staged module's compiler identity normalized to the baseline for that comparison. Thus dependency rows, generated requests, request digests and all other output fields must be identical. Separate tests retain the real staged source identity and prove it changes the environment. Nine concrete invalid parameter/time/key/context cases compare baseline and staged refusal codes.

Reproduce only this lane's pure tests with `python3 -B artifacts/implementation/pat-environment-extraction/run_tests.py`; each run creates a new attempt directory. The sealed index is historical and will then need a new, separate seal rather than silently replacing old evidence. `verify.py` validates the sealed files and attempt receipts offline; `--compare-live` additionally compares the captured original sources against the checkout, which is expected to differ after later authorized integration. Endpoint equality does not detect edit-and-restore or provide an atomic filesystem snapshot.

No Runtime, worker, model, hardware, native controller or acquired research program was executed by this lane. Pure compatibility cases are finite regression evidence, not a proof over all possible artifacts. Simulation qualification/provider configuration, finite behavioral trials, promotion, public mounting, learning and device I/O/hub work remain pending.
