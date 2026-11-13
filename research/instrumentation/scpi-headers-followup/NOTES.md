# SCPI headers: review and HMS consequences

Source: the retained [SCPI-99 PDF](../raw/scpi-99.pdf), Volume 1 Chapters 5–6, printed pages 5-1–6-10, PDF pages 22–33; [extracted text](../text/scpi-99.txt), LF lines 971–1570. The source is a 1999 edition, not a claim about current instrument support. Its IEEE 488.2 references still require a separate reading. The interpretations below are HMS design conclusions, not functionality supplied by SCPI itself.

## Native command semantics

The notation table and indented command tables distinguish optional nodes, alternatives, parameters and short/long spellings. The two page-24 railroad diagrams distinguish common commands from hierarchical instrument commands: the former require a leading asterisk; the latter permit a root colon, repeated mnemonic components, numeric suffixes and a final query marker. The text extraction omits these diagrams, so text-only review would leave a material grammar gap.

Only the defined short and long mnemonic forms are valid, with case ignored. An arbitrary prefix is not another legal abbreviation. Naming and hierarchy rules seek consistent operations across instruments, while permitting absent fixed or unsupported functions. Therefore a shared vocabulary does not prove that every device implements a command. A provider needs the exact supported grammar and parameter contract.

Optional/default nodes preserve the meaning of an individual command but do not insert themselves into the parser's remembered path. Relative commands in a compound message resolve using the explicitly transmitted header. The examples on pages 30–31 show that an earlier command can take effect before a later header produces an error. HMS must not interpret a compound-message syntax failure as atomic rollback. A future provider should build complete native commands from validated typed actions, validate the whole sequence before dispatch, serialize the session and retain uncertainty if a sequence is interrupted. Prevalidation reduces avoidable errors; it cannot supply physical atomicity or prove what a disconnected instrument executed.

Query forms ordinarily report settings without changing instrument settings or couplings, but the measurement subsystem is an explicit exception. A question mark consequently cannot serve as a read-only authorization test. Earlier reviewed status/error operations also require their own effect definitions. The provider must declare whether a query triggers acquisition, changes state, consumes a queued result or affects couplings. Responses need explicit units and documented unit-setting dependencies; a numeric value alone is insufficient.

## Resource and data models

SCPI separates electrical-port selection, duplicated independent capabilities and separately addressed logical instruments. A numeric suffix selects the duplicated capability at the relevant node. A multi-capability device interprets an omitted suffix as capability one; a single-capability device need not accept an explicit suffix. A generic emitter must not append a digit merely to normalize wire spelling. Separate logical instruments have separate status models and I/O buffers, even when they share a physical chassis or bus.

For HMS, these distinctions imply explicit physical-resource aliases, per-logical-instrument response ordering and shared-bus ownership. They do not justify equating a connector, channel, instrument identity and transport session. Discovery must retain those relationships instead of flattening them into one device identifier.

Similar command names can control distinct functions. The reviewed input-versus-sense attenuation example differs in compensation and reported measurement values. Sensor averaging and calculation averaging likewise differ in purpose and data lineage. A capability schema should retain calibration, acquisition and postprocessing meaning; matching names do not establish resource identity or interchangeable results.

The header-design rules reject parameter syntax whose arity or type changes according to another parameter, favoring separate hierarchical operations. This supports closed typed HMS actions with explicit parameter schemas. It does not automatically validate a generated PAT or establish a universal shell on Arduino-class devices.

## Consequences for prompt-to-PAT and hub control

A deterministic PAT should call an installed typed provider, with native spelling, parser/session state, response association and physical effects owned by that provider. Applicability must include the instrument profile, firmware/configuration, units, calibration and required capabilities. A changed driver or reconnected session can invalidate those dependencies; a previously successful command string is insufficient evidence for reuse.

The hub needs ownership of the relevant adapter/session and bus resources, alongside compute and storage admission. Raw SCPI access, if exposed, needs an explicit effect envelope and the same resource arbitration as high-level actions. Neither standard command syntax nor an LLM's confidence supplies a fence, completion proof or safe retry policy.

Remaining work includes the rest of SCPI-99, IEEE 488.2, chosen VISA/GPIB/USBTMC/VXI-11/HiSLIP/LXI transports and exact vendor manuals. This overlay establishes no security, timing, transport-lock, conformance or physical-validation claim.

## Visual reading ledger

| PDF pages | Reviewed material |
|---|---|
| 22–23 | Notation table, hierarchy/default-node and alias examples, explanation of syntax diagrams |
| 24 | Both header syntax diagrams; abbreviation rules |
| 25–27 | Mnemonic construction, tree rules, parameter/hierarchy examples |
| 28–29 | Optional functionality, distinct measurement/postprocessing semantics, query rules |
| 30–31 | Units, relative path examples, default-node parser state, port/capability distinctions |
| 32 | Numeric-suffix compatibility and separate logical-instrument buffers/status |
| 33 | Blank chapter-ending page with running header and pagination |
