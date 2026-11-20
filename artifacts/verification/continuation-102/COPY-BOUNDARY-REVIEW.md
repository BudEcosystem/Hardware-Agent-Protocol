# Encoded-copy and finite-frame source review

Root fully read the three-file project diff, REVIEW, CONTROLS, PLAN, README and
independent-review note. The seven substitutions preserve each encoded eight-byte
read-before-write snapshot with memmove; twelve literal UINT64_MAX writes become
eight-byte 0xff fills. Surrounding writes, callbacks, arithmetic and validation
order remain unchanged. This does not broaden caller-buffer alias guarantees.
Only poll_finite gains a conditional GNU noinline attribute. Other compilers remain
source-compatible and unqualified for this stack-boundary assertion.

The new complete controller control exercises a high-bit timestamp across a
32-bit carry and a separate near-maximum timeline. Its literal byte oracles cover
OPEN, renewal, actual output handoff, private loss handoff/redaction, aggregate
witness, ACK and RESUME, plus clock-loss absent fields. All thirteen earlier case
bodies remain exact, giving fourteen proposed cases. The delegated independent
review traced the fixture timeline and found no concrete defect; root's source
review does not itself establish those cases passed.

The original 93-file source proposal is preserved under history/source-proposal,
index SHA-256
`f2387700d92b528162376291ad01d6a9ceca6b2d53f05c8cc01fb51fe681f253`.
Root independently checked all historical bytes, all 36 project and baseline
copies, thirteen unchanged case byte spans, owner inputs and retained input pins.

Root then fully read the exact runner delta, RUNNER-REVIEW, PROFILE and the
entrypoint's snapshot/finalization body. Process ownership, cleanup, tool/plugin
selection, target, roots, options and limits are unchanged from the corrected
sealed LTO runner. New gates retain the exact finite/runtime baseline counts,
require fourteen standing cases and matching complete plain/sanitized reports,
and record the observed new assertion count. No guessed count becomes evidence.

Reviewed runner SHA-256:
`f7d68720933746abb2bdd335048fac6413dc43c4001063214a86bd04ea65c786`.
Reviewed final metadata SHA-256:
`e37adaad24506bb39f975b8d942791aa39c844e411422aac2979b509deb724f9`.
The root preflight records exact inputs before authorizing the fixed native stage.
An AVR compile/link attempt remains separate from target execution. Generated
finite/standing frame lifetimes, complete stack/ISR coverage and flash fit must be
measured; the source attribute and arithmetic reservations do not prove them.

## Retained execution and generated boundary

Root executed the unchanged reviewed native runner, then the separate AVR stage
with the retained explicit toolchain. The native stage passed all fourteen standing
cases / 766 assertions in both plain and sanitized modes; finite and runtime
controls also passed. The AVR stage compiled all twelve units but failed the
physical flash link by 9,042 bytes. Its failed map charges 41,810 flash bytes,
82 fewer than the parent LTO profile, and 1,503 static bytes. No final ELF or target
execution exists. The root-run data audit passed all thirty-seven command/reap
joins and original source/tool/public-input checks.

Root read the complete current wrapper assembly and finite prologue, then the
complete generated-boundary report, results and next-work notes. The delegated
review read the complete finite callee as well. The saved backend shows six saved
caller bytes and no finite local frame on the standing-call path, compared with
the parent's 83 local plus eighteen saved bytes. This is a local 95-byte reduction
at that call only; no maximum application stack or ISR bound is established.

The independent root text verifier reproduces every range hash and instruction,
call, push/pop and stack-pointer record for both complete current units, all
function/storage roots, failed-map arithmetic and compiler artifact inventories.
Its first two invocations exposed verifier parsing errors: aggregate `.text`
must exclude discarded input sections, and libc bodies use `.text.avr-libc` with
object/symbol identity. Those parser corrections changed no candidate or report
bytes. The third invocation passed and retained an exclusive result. This is data
verification; it did not rerun the compiler, auditor, native suite or target.

The independent reviewer reproduced the same data joins and verified all 65
current/frozen input pins for both attempts. The section separation itself costs
eighteen additional text bytes; the complete candidate's measured net reduction
remains only eighty-two bytes. Further flash fit, complete final stack accounting,
UART instruction review and physical timing/I/O qualification remain open.
