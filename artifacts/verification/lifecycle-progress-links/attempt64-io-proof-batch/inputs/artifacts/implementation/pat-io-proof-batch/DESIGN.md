# One static snapshot per pure definition build

The measured current worker repeatedly parses the same topology and generation
document while constructing an installation's instance definitions. Reuse one
detached, validated snapshot within that pure call, retaining a separate complete
proof derivation, proof-schema validation, canonical bound and detached result for
every instance. Do not change `check_tree` or adopt the rejected validator candidate.

The private builder is created at the original first-handler proof point. Original
handler, consumer and electrical-property lookups therefore keep their precedence
over topology/generation validation. Public `binding_proof` and `handler_details`
still parse fresh inputs on every invocation. A replaced installation-level public
proof helper takes the original path. The build assumes trusted pure helpers and
no mutation of its input during a call, as the preceding action-proof reuse did;
concurrent mutation or malicious Python monkeypatching is not an authority model.

The builder lives only in a local cell, retains at most one bounded topology and
generation snapshot plus their graph indexes, and cannot appear in returned JSON.
No value survives the call. Current authority, source identity, endpoint session,
claims, provider state, database and effect checks remain separate and unchanged.
This is pure static construction, not a cache of permission to operate hardware.

Two production modules change. Baseline proof and definition bodies are retained
as AST-checked differential references. Existing instrumentation counts the new
shared per-instance derivation helper; its eight-versus-four and ten-versus-four
semantic checks remain. The literal actual-import consumer identity is recomputed
from the previously audited image inventory using current source bytes, and still
needs runtime equality verification. No failed logical run or old receipt is reused.

Pure controls must verify exact outputs, refusal order, detachment, changes between
calls, public freshness, current helper fallback, concurrent independent calls and
actual validation-call reduction. Fixed interleaved timing is descriptive only.
After passing controls, the complete 30-case worker and vault import must still
meet the original 60-second worker and 180-second parent bounds. Device, driver,
hub, persistent MCU and natural-language learning requirements remain unchanged.
