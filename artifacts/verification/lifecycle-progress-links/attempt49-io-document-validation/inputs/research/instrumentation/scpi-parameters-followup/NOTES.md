# SCPI parameters: native semantics and HMS consequences

Source: retained [SCPI-99 PDF](../raw/scpi-99.pdf), Volume 1 Chapter 7, printed pages 7-1–7-10, PDF pages 34–43; [extracted text](../text/scpi-99.txt), LF lines 1571–2054. The statements below describe this edition. Native model support and referenced IEEE 488.2 rules require their own review. Proposed HMS consequences are distinguished from source semantics.

## Numeric values are a behavioral contract

The source requires rounding to an accepted nearest value and leaves the resulting parameter value unspecified for an out-of-range request. Consequently a range-error response alone cannot prove that the prior setting survived. A future HMS binding needs the instrument's accepted domain, resolution, quantization/tie rules, coupled constraints and post-error reconciliation. Validate the resulting setpoint envelope and record requested versus actual settings; do not silently equate rounded command acceptance with the requested physical outcome.

MIN/MAX denote limits currently available for a function. Defaults can depend on the model and operating configuration. Optional special forms are supported command by command. For deterministic PAT reuse, these are contextual operations or explicit resolved values with provenance, not universal constants. A discovery-time limit is not a lease over future configuration. Multiple-parameter limit queries have their own positional arity rules, so typed operation schemas must represent the complete native signature.

UP/DOWN change the current setting according to linear, logarithmic or preferred-number stepping and may use automatically coupled increments. They are relative effects: repeating the same native command can advance again. A stored successful trace must not turn them into a generic retryable set operation. A PAT needs the admitted operation identity, step-mode dependencies and bounded resulting range. Recovery must resolve the original effect rather than repeat an uncertain increment.

Page 36's formulas were checked visually because the extracted floor/ceiling notation is damaged. The logarithmic formulas operate on the log-scaled step index before selecting the next higher/lower point. The example on page 37 illustrates three steps per decade. No formula was executed, and behavior outside the documented logarithmic domain is not inferred.

## Special results and strict host types

SCPI uses decimal sentinels for positive/negative infinity and for NaN; NaN can also mean missing trace data. These are not ordinary large measured values. The same chapter states a general numeric range and then describes a NaN sentinel above it. A binding must resolve that special-form treatment using the command and instrument profile, rather than applying one guessed global finite-number rule. This review records the apparent range/sentinel tension without claiming the remaining standard or vendor documentation resolves it.

An HMS adapter should preserve the original bounded native representation and expose an explicit result category for nonfinite/invalid data. It must not coerce the value to zero, an enormous finite reading or unsupported JSON NaN/Infinity. NaN alone does not distinguish missing acquisition from arithmetic failure; report an unknown reason unless additional evidence resolves it. The current bounded host number profile remains unchanged by this research.

Native Boolean input also differs from strict JSON typing: the source permits numeric input that is rounded to an integer and then interpreted by zero/nonzero, while query output is numeric zero or one. A typed HMS Boolean provider should emit the explicit supported Boolean form and preserve strict caller types. It should not make the instrument's permissive numeric coercion an implicit host behavior. Referenced rounding details, including boundary cases, still need the IEEE/manual review.

## Coupling expands the operation's effects

Functional coupling can cause a setting command to change an operating mode or start work. The source calls for uncoupled primitives and documentation of the primitive sequence behind a composite operation. Value coupling can modify several related settings; automatic coupling may depend on other settings or physical input. Therefore a provider's declared effects and resource footprint must include the complete coupling dependencies, not merely the field named in the command.

Explicitly setting a value can disable its automatic coupling. AUTO ONCE computes a value for present conditions and then leaves automatic mode off; a later Boolean query cannot prove that the one-shot event occurred. The operation receipt and resulting observation must retain that history. Stable PAT code does not make environmental inputs or instrument algorithms deterministic. Reuse needs an applicability envelope, effect guards and outcome checks covering the permitted variability; unfamiliar conditions return to the agent.

## Units carry configuration and measurement meaning

An explicit suffix overrides default units; absent suffixes can depend on the UNIT subsystem and reset state. Conversions between amplitude and power need the specified impedance. Peak, peak-to-peak and RMS qualifiers distinguish measurement meanings, and the default qualifier can be device-dependent. The page-41 equation and example were visually checked. Do not infer a waveform-dependent conversion or impedance solely from a unit string.

For HMS, retain unit, amplitude convention, impedance, calibration and relevant configuration identity with settings and observations. A driver or hub analysis job must preserve this lineage through conversion. A bare number in a stored trace is insufficient evidence for a reusable scientific PAT. Unitless ratios and logarithmic differences also have distinct meanings; a unitless gain cannot silently become a percentage or dB value.

## Visual coverage and remaining work

| PDF pages | Material reviewed |
|---|---|
| 34–35 | Reset/default semantics, accepted numeric range, current MIN/MAX, optional relative steps |
| 36–37 | Step syntax, both logarithmic formulas, preferred-number sequences, examples, infinity/NaN sentinels |
| 38–39 | Suffixes, native Boolean coercion, functional/value coupling, one-shot automatic behavior and primitive/composite examples |
| 40–41 | Automatic coupling, linear/logarithmic units, impedance equation and example, amplitude qualifiers |
| 42 | Unitless ratio and logarithmic-difference semantics |
| 43 | Blank final chapter page, running header and pagination |

Finish the remaining SCPI text, IEEE 488.2 parameter rules, chosen transports and exact vendor manuals before implementing a conforming native parser or physical provider. Existing public GPIO/PWM simulation and host PAT tests do not establish those instrument behaviors.
