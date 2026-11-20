# Native checks pass; original AVR target still does not fit

Root executed the reviewed frozen candidate once in each stage. Native checks passed. All 13 AVR units compiled, but the linker failed with 6,418 bytes of physical flash overflow. The failed map charges 39,186 flash bytes: 716 fewer than the shared-kernel parent, still 6,930 above the unchanged 32,256-byte application allowance. There is no linked ELF, runtime-fit demonstration or complete stack proof.

This current result record supersedes the unexecuted status in the frozen preparation documents. README, PLAN, REVIEW, controls/runner notes and project-source-review.json remain exact historical inputs; none of the 139 frozen bytesets was rewritten after execution.

| Native evidence | Actual observation |
|---|---|
| Original finite suite and pipe | 26 cases / 2,548 assertions / 20,000 malformed inputs; pipe checks passed |
| Runtime integration | 11 cases / 143,471 assertions / 20,000 wire-oracle steps / 256 interrupt snapshots, plain and sanitized |
| Original standing controls | 14 cases / 766 assertions, plain and sanitized |
| Numeric controls | 6 groups / 86,889 assertions for byte and scalar-fallback backends, each plain and sanitized |
| Controller equivalence | 20 groups / 1,617 assertions and 1,177 state records; all six parent/byte/fallback traces are identical |

The differential total includes 851 assertions beyond the old standing766, or 376 beyond the parent's 1,241. The common complete trace SHA is `6eda3f924f18792751bd0ff643d1c53cb7bc3684c94a828de5c4f91572f0adc2`. These are fixed-corpus native observations. The direct private accounting and seeded loss-counter controls retain their explicitly documented scope; they do not establish physical reachability or qualification.

The [native receipt](checks-native.json), SHA `44a4b3ccd0c9ae75bc6e3d578cc15f16e38c4b1cec7007a2a6b190bbd7e0383f`, retains 34 outer commands and reaps. The [AVR receipt](checks-avr.json), SHA `b8a911b2a15ea4e8aa41791f80bb0d5193b2a1fa5ccbe7f418169a9b3a92d81f`, retains 24 commands and reaps, with avr-link as the sole failed command. Both attempts are preserved without reruns.

The [failed map](build/avr/runtime.map), SHA `12336960e81dbb8d6dd998ea2d061fabb5db1df8a509a1bd8d9a50585610328c`, has `.text`39,160, `.data`26, `.bss`1,477 and `.noinit`0. Thus flash is39,186 and static SRAM is1,503, the same exact160-byte delta over1,343. Static plus the existing512-byte stack reservation is2,015, leaving33 bytes arithmetically. These are failed-map section calculations; they do not validate a linked image or establish the actual combined stack requirement. The 716-byte reduction is the combined candidate/profile result, with no invented per-edit savings.

Root reviewed and ran the [retained-data auditor](audit_retained.py) once. [AUDIT.json](AUDIT.json), SHA `0abbf1e42573747137e07e84659e0079b85e08e55faa60a5a94d37688574d61d`, passed its joins: 58 commands and reaps with observed identities absent; all139 frozen inputs,41 project files,40 exact originals,19 old control bodies and244 public inputs exact; runtime/tool/plugin/alias evidence stable. Its AVR outcome explicitly remains failed, with58 generated artifacts and no ELF. The auditor marks failed-map resource arithmetic unaudited; a separate reviewed retained-text reader now supplies those map/body joins.

The [generated-text measurements](codegen-measurements.json), SHA `45ac1f93734f34a9004de16c2744f3d2a60d33cf5b4e6c3f3196769b6d126e00`, join all146 emitted bodies (38,606 bytes) plus554 other text bytes to39,160, and then26 data bytes to39,186 flash. All30 function roots, nine charged storage roots and serializer aliases remain. Emitted owner totals change by kernel-674, finite+158 and standing-200 bytes; all other owner totals are unchanged. These are disjoint generated-owner totals, including inlined descendants, not isolated source-edit savings.

The first reader attempt refused a mistaken classification of a local-allocation push as a saved register and wrote no result JSON. Its exact source and [transcribed root tool return](reader-history/draft01/attempt01.json) are retained. Root reviewed the narrow correction distinguishing local allocation from explicit register/IRQ saves, then executed the corrected reader successfully. This was a data-reader correction; no compiler, candidate or target was rerun. The corrected reader SHA is `ca53285a3813df8357b08e3c5052a8fefa51667721074b0ee7442a6e536fb58a`. Automatic body/frame joins and manual relevant-body review still do not establish a complete reachable stack bound.

No AVR image, emulator, physical device or driver was executed. The target, ABI, complete uint64 domain, retained services/roots/storage and reserves were unchanged. A further substantial whole-image reduction and valid-link stack/ISR/callback evidence are still required for this original-board profile. Host durable/PAT integration and physical I/O qualification are separate remaining work; native controller equality does not complete the full system goal.
