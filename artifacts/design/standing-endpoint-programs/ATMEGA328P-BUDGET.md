# Original target: proposed allocation ceilings

This is a design budget, not a compiled size or target-support result. The exact starting evidence is the sealed [combined stack assessment](../../implementation/avr-link-integration/STACK-REVIEW.md) and [machine-readable result](../../implementation/avr-link-integration/combined-stack-analysis.json): declared 16 MHz ATmega328P, 2,048 SRAM bytes, 32,768 physical flash bytes, 32,256 UNO application bytes and 1,024 EEPROM bytes.

| Baseline quantity | Retained value |
| --- | ---: |
| Linked flash | 21,778 bytes |
| Static SRAM | 1,343 bytes |
| Stack reservation | 512 bytes |
| Current conservative foreground | 295 bytes |
| Current computed maximum non-nested ISR, including extra margin | 38 bytes |
| Retained ISR planning allowance | 64 bytes |
| Retained future callback-growth allowance | 128 bytes |
| Current planning stack requirement | 487 bytes |
| SRAM outside static plus stack reservation | 193 bytes |
| Unassigned bytes inside planning stack reservation | 25 bytes |
| Full primitive/driver persistent-state allowance | 256 bytes |
| Separate protection-service storage reservation | 64 bytes |

The first profile cannot add another 192-byte program store, a second parser, an unbounded sample queue or a standalone per-event EEPROM journal and still cite the old fit result. Instead it makes the explicit single-slot tradeoff: a tagged standing record retains its immutable OPEN bytes in the existing 192-byte operation buffer when and only when the finite OP/receipt slot is empty. No finite receipt is overwritten, and all finite admissions refuse while that standing record remains. The buffer tag must be enforced inside the common core and covered by native regression tests; it is not a convention that callbacks may ignore.

## New protocol state: 128-byte design ceiling

The [retained-field reconciliation](MEMORY-RECONCILIATION.md) gives every field, offset and equality/reuse assumption. This is an allocation worksheet, not a transmitted C struct or an established ABI. Actual compiler `sizeof` and the complete linked image must verify the ceilings. Immutable identity/configuration/fence/initial-lease bytes are read from the tagged OPEN buffer; they are not also charged as duplicate protocol fields.

| Group | Bytes |
| --- | ---: |
| Standing high-water, slot kind, current lifecycle revision, last mutation sequence and exact 20-byte comparison body | 33 |
| Current lease, activation/ACK watermarks, next service, first loss, cleanup deadline, quiescence time, two pinned input epochs and completed commanded-on accounting | 60 |
| Lifecycle/drain/service states, separate ownership/quiescence masks, first reason, explicit flags, ledger indices, pending feedback and loss-command state | 13 |
| Dedicated aggregate quiescence witness | 22 |
| **Total new standing protocol state ceiling** | **128** |

Installer/configuration pointers, dispatcher glue, ABI padding, new static constants in SRAM and any arbiter fields must together fit a further **32 bytes**. The entire new static-SRAM delta is therefore capped at **160 bytes**, not merely the named struct. If implementation needs more, it fails this design budget; the omitted bytes cannot be hidden in a caller's stack or an uncounted global.

That ceiling gives `1343 + 160 + 512 = 2015`, leaving 33 SRAM bytes outside the unchanged stack reservation. This is an arithmetic target only. The complete image may use less or may fail; no standing image has been built. Flash growth is capped at 10,240 bytes, giving at most 32,018 of 32,256 application bytes. The residual 238 bytes are not an invitation to omit bounds or drivers.

## Preserve and partition the 256-byte primitive allowance

The initial original target carries a 50-byte synthetic fixture plus a 206-byte reserve. A new installed controller may use that existing **full 256-byte allowance**, but the total remains reserved and charged. The first allocation proposal is:

| Installed-controller storage | Ceiling |
| --- | ---: |
| Finite/sensor/output driver persistent state (including original 50-byte fixture if retained in the image) | 64 |
| Immutable normalized kernel configuration | 32 |
| Controller working state | 24 |
| Two observation records, 24 bytes each | 48 |
| Two retained transition/feedback records, 44 bytes each | 88 |
| **Total** | **256** |

Each observation budget covers signed value4, acquisition tick8, source sequence4, source epoch4, quality1, continuity1, accepted-sample-pending-evaluation1 and reserved-zero1. Publication sets the pending flag only for a newly accepted sample; evaluation clears it, so duplicate publication cannot invent a new trigger without an uncounted last-evaluated sequence. Foreground phases own these records; ISR acquisition state remains in the charged driver allowance. The controller's 24-byte working budget can hold last-transition tick8, feedback deadline8, baseline demand4 and four state/index bytes. Global next-service/loss deadlines are already charged in the protocol state.

One 44-byte transition worksheet is activation number4, output dispatch tick8, demand sequence4/value4/age2, feedback sequence4/acquisition tick8/value4, four explicit tail bytes and reason2. The tail is previous output, requested output, bounded execution/possible-effect/verification flags and evidence-kind/quality flags. Producer epochs are fixed by OPEN and the two separately pinned epoch fields; a change stops the instance before reuse. Demand age is bounded below 60,000 ms and reconstructs its acquisition tick exactly from the dispatch snapshot. Pending feedback uses an explicit absent timestamp/state; a command echo is not successful feedback. This is a field budget requiring a final closed layout and independent codec tests, not a compact encoding already implemented.

The separate 22-byte quiescence witness supports one installed aggregate predicate for the complete owned mask. Standing partial release or multiple independent retained witnesses are outside this first profile. First-loss ordinary observations/controller state freeze; bounded loss acquisition uses driver scratch and this witness without overwriting a full ordinary ledger. The 32-bit cumulative field counts completed commanded-on milliseconds against an installed fixed limit; it is not a physical energy integral. Renewal/resume cannot reset it. These restrictions, including exact resumed-evidence collection, are part of the memory contract rather than optional optimizations.

The 32-byte kernel configuration can hold lower/upper demand bounds8, required response improvement4, minimum feedback value4, six `u16` durations (sampling period, two maximum ages, minimum on/off dwell and feedback window)12, and four output/policy bytes. Units, permissible numeric ranges, supported output/loss values and physical predicates are pinned by the installed kernel/driver manifests. The program may vary supported parameters without firmware rebuilding; adding unsupported semantics or an electrical peripheral may still require a new installed driver/kernel and commissioning.

A two-record ledger is small: a disconnected system can make at most the remaining unacknowledged ordinary transitions before it must stop accepting further ordinary transitions. It must not claim unlimited offline control or full trace retention. More records, more inputs, arbitrary program bytecode, concurrent OPs or persistent event replay require a separately budgeted profile.

## Stack and service constraints

With the prior 64-byte ISR and 128-byte future-callback allowances retained, a standing implementation's conservative foreground maximum must be at most `512 - 64 - 128 = 320` bytes, and startup must also fit the complete reservation calculation. Only 25 bytes of foreground growth are available under that scenario. Dispatch standing parsing/control as a sibling of the finite handler, rather than nesting it inside an already deepest finite path. Reuse caller-owned bounded output storage; do not create a 192-byte automatic copy of the OPEN packet or ledger. The resulting graph must be derived from the exact linked image, including every new callback and helper, rather than assuming sibling dispatch guarantees the bound.

The current actual IRQ paths fit below the preserved 64-byte allowance. Any added ADC/tachometer/timer ISR, nested interrupt policy, library callback or acquisition buffer requires fresh combined analysis. Timer1 remains exclusively owned by the qualified clock profile; a PWM or acquisition driver cannot quietly reconfigure it. Board-specific timer/pin/bus aliasing must be included in the resource map. A driver needing over 64 bytes of the proposed driver slice or more stack/IRQ space cannot borrow the independent protection reservation.

The existing 64-byte protection object is still only a reservation, not a physical stop implementation. A real installation must implement and account for that service and prove its required independence/timing. A successful synthetic controller build would leave this physical qualification open.

## Explicit unsupported-fit result

Until actual code passes the unchanged native finite tests, standing tests and a new exact AVR cross-link/stack analysis, the support result is **design only; target fit not established**. If any global static delta exceeds160, controller allowance exceeds256, combined stack scenario exceeds512, application flash exceeds32256 or service deadlines are unqualified, reject this ATmega328P profile. Preserve the failure and either reduce the explicitly advertised controller feature set without weakening correctness, redesign measured storage/call paths, or select a separately identified larger-target profile. Never silently increase SRAM/flash, remove clock/boot/RX/TX/stop accounting, shrink retained allowances or claim that a finite OP loop satisfies the missing standing feature.
