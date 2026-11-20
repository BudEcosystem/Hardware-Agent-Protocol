# Machine-readable draft

`device-description.schema.json` formalizes a small description subset of the proposed standard. The three example files are deliberately marked `design_example` and `unmeasured`. Values are synthetic, not installation limits. This schema is not an official MHS format.

The [WoT reuse decision](../docs/wot-reuse-decision.md) supersedes this custom format as the public discovery direction. Keep it as an exploratory physical-contract input. `examples/wot/` uses the pinned official informative TD 1.1 schema plus narrow HMS lint; run `python3 scripts/check_wot_profile.py`. TD validity and a declared profile do not supply runtime admission, strict request validation or physical evidence. See the [profile boundary](../spec/05-description-profile.md).

Run `python3 scripts/check_descriptions.py` with Python 3 and `jsonschema` installed. It checks shape, finite values, identifier uniqueness, resource/observation/limit references, unit identity and bounds. It does not validate the truth of metadata, calibration, electrical compatibility, physical safety or executable support. Input schemas require additional semantic comparison with parameter definitions before runtime admission can rely on this format.

`invoke.schema.json` now defines an experimental strict host invocation envelope; [host profile](../spec/08-host-contract.md) specifies JCS/digest, replay namespace and numeric/timing rules. `hms/contracts.py` adds parsing constraints JSON Schema alone cannot enforce. `hms/journal.py` exercises durable operation storage with synthetic policies. These are separate from the earlier WoT example action shapes, which still need an explicit projection update.

Still to specify or integrate: enrollment, observation and operation wire envelopes; authentication/delegation; protocol negotiation; event/error schemas; procedure IR; compact MCU operation payloads (framing exists); stream/data references; registry federation; full compatibility fixtures. The current schemas are experimental and may change incompatibly before 1.0.
