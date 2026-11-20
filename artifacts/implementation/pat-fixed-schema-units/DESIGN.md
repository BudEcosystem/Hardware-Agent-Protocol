This is a source-only pure compiler extension staged against the exact 151 inputs retained by full748 attempt `20261107T014321.791506Z-b4b2085264e7`. The baseline and sealed I/O PAT design inputs are copied and pinned in `baseline-inputs.json`. Nothing in this stage has been imported or executed. No I/O binding provider, worker, public service, device model, or qualification is added.

The legacy argument metadata remains exactly:

```json
{"unit":"percent","frame":null,"unitArgument":"unit","frameArgument":null}
```

The new, explicitly tagged alternative is exactly:

```json
{"profile":"hms.pat.argument.fixed-schema-unit/0.1","unit":"ms","frame":null,"unitArgument":null,"frameArgument":null}
```

All five keys are mandatory and additional keys refuse. The profile must match exactly. Both the type schema and concrete binding schema must describe the argument as `integer` or `number` within the compiler's existing finite scalar grammar. The unit must be an explicit non-null identifier under the existing bounded semantic grammar. Frame and both companion fields must be null. This initial extension supports fixed units only; fixed coordinate frames and nonnumeric semantic values remain unsupported.

The unit is an opaque exact label, not a conversion registry. Trusted installation setup chooses it; the compiler cannot attest that setup or infer meanings from field names. For an eventual finite I/O registration, the proposed labels are level=`1`, duration=`ms`, frequency=`Hz`, duty=`permille`, and resolution=`bit`, with null frames. These are examples for future trusted registration, not an automatic mapping implemented here. `s` does not equal `ms`, and `percent` does not equal `permille`. No alias, conversion factor, arbitrary callback, application-supplied metadata installation, or new public request field is added.

A short branch in `_binding` validates tagged entries and then leaves the legacy validation block byte-for-byte intact. Unknown profile tags never fall back to legacy. Legacy non-dimensionless numeric values still require string companion arguments. Legacy frame companions, nonnumeric null semantics, and dimensionless numeric metadata keep their original rules. An action may mix tagged numeric entries with legacy entries, but each entry is checked by its exact grammar. Existing installed registrations are not rewritten or upgraded.

Existing full declared-domain inclusion applies to both schemas before lowering. Parameter units and frames must exactly equal trusted argument metadata. A literal is already interpreted in the declared fixed schema unit; the compiler copies its exact value, without creating a unit argument or conversion. Bool/integer/integral-float distinctions remain those of the existing PAT parser and scalar checks. Narrow applicability cannot excuse an invalid declared domain. This unit extension does not prove that duration fits an execution budget or that a primitive can complete; the separate I/O policy must supply the strict timing/domain qualification described in the sealed design.

The tag and unit are retained in the existing `metadataDigest` and environment `argumentMetadataDigest`; the complete binding document also contributes to `runBindingDigest`. Existing type and binding digests identify the two schemas, so no duplicate schema digest field is introduced. The compiler source is already in its implementation identity closure: changing this validator changes compiler identity and environment/run identities even for legacy artifacts. Legacy request bytes, request digest, PAT digest, and semantic validation are expected unchanged; implementation-dependent digests must not be presented as unchanged. Endpoint session remains excluded from static environment and retained in dependencies and concrete requests.

The staged tests will cover fixed-unit GPIO-shaped/PWM-shaped scalar contracts using original pure fixtures, exact labels under opaque argument names, closed metadata, no companion synthesis, wrong units and scalar kinds, bool/float refusals, whole domains and enum holes, narrowing applicability, literal handling, dependency identity/session separation, detached inputs/outputs and call-time absence of I/O. They also retain legacy companion checks and the existing three-family pure environment suite. Test definitions and structural comparisons are preparation, not passed test evidence. Runtime, physical support, and I/O qualification remain outside this stage.

The full748 baseline compiler precedes the separately owned IDNA dependency-identity correction. This stage preserves that historical compiler identity code byte-for-byte; it does not absorb or validate that concurrent fix. Any later integration must rebase the small validator branch onto the then-current compiler and regenerate evidence for that exact closure.
