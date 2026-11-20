# LTO source/profile review, continuation 101

The root read the complete runner delta against the sealed fit runner, the
candidate PROFILE, PLAN, REVIEW, RUNNER-REVIEW and README, the complete retention
and toolchain pin files, and the source review record. The unchanged owned-runner
lifecycle was previously reviewed in the sealed controller/fit lanes. No new
claim of reading every file in those packets is made here.

Frozen runner SHA-256:
`dfc11868dd929b043f036158a4a77bceb02edd8cc407f05548aefc5d354cd537`.
Runner delta SHA-256:
`9cc4f70fe315b751d4fc263505a21bd11d1f01992f8c88791b97057f1fc55805`.
Source review SHA-256:
`cfd4ea8897addb00b51824fe09543eaf9cb243823bbf996a1353c128f921f0b8`.

Independent read-only joins verified:

- All 36 project files equal both their original copies and the sealed fit
  project; no native source changed.
- All 24 selected compiler/backend/plugin/spec/library file or alias entries
  equal the retained official archive. Host make and shell bytes also match.
- All four runner owner inputs equal the sealed fit copies.
- All eleven metadata pins in the source review match current bytes.
- All 29 function roots and nine storage roots have allocated symbol entries
  in the exact parent failed map, not merely names in discarded sections. The
  nine charged storage objects total 1477 bytes.

The build uses matching `-Os`, one-job/one-partition LTO, fat objects, linker
plugin and diagnostic options at compile and GCC-driver link. It preserves
the target, physical/application flash ceilings, all static reservations and
the 512-byte stack allowance. The explicit root policy newly forces 26 already
present function symbols and nine already present objects; size comparisons
must disclose this change. Host libraries and dynamic loader retain the prior
trusted, unpinned scope.

The constructed environment pins make and the possible recipe shell, supplies
a private temporary directory, and inherits no make/jobserver flags. The runner
checks alias targets along with file hashes. Original child ownership, signal
masking, process/resource limits and terminal failure publication remain.
Post-settlement inventory retains generated backend artifacts on failure as
well as success. Conventional fat-object stack records are explicitly pre-LTO;
the runner never treats their presence as final stack proof.

After these reads and joins, the root authorized one AVR build attempt with
the explicit pinned retained toolchain-bin path. The inherited default path is
stale. Native tests are not rerun because their complete source is unchanged.
No target, emulator, physical port or firmware execution is authorized by this
review. The actual attempt receipt determines the result. A successful link
alone cannot establish complete foreground/ISR stack, UART timing or hardware
qualification.

## Plugin lookup correction and second attempt

The first attempt retained nine successful driver queries followed by a path
validation refusal: `-print-file-name=liblto_plugin.so` returned the unresolved
basename. No C compilation or LTO backend execution occurred. The independent
`AUDIT-ATTEMPT-1.json` joins those nine command/reap records and observes all nine
original process identities absent. The initial audit source is retained as
`audit_retained-attempt-1.py` at its original SHA-256
`3a6ac04e30a37d8c008a5b8a3f1d9aabf8373385bf615a12ef912edc24ab2b79`.

The root read the complete narrow runner correction, its review note, the
research notes and exact source coverage/pin records. The root also read the
complete upstream `for_each_path`, `build_search_list`, `access_check`,
`file_at_path`, `find_a_file`, `find_file` and `maybe_run_linker` functions and
the relevant print-query branch. The delegated research separately records its
larger complete-function reading scope; neither claims both GCC source files
were read in full or match the downstream AVR source byte for byte.

GCC's ordinary-file query uses start-file prefixes, while actual linker-plugin
selection uses executable prefixes with `R_OK` and no multilib traversal. The
corrected runner obtains the ordered executable-prefix list using the same
profile's `-print-search-dirs`, reproduces first-readable selection, and requires
the winner to satisfy the existing archive/path/alias pins. It does not substitute
an executable-permission query or skip an unexpected readable winner. The parser
and prefix count are bounded, and selection is observed before and after later
commands and at final cleanup. This does not establish filesystem immutability.

Second runner SHA-256:
`4764793f5ea549c0b067ab2a343b98e1e3d301a85dcbb801741b26ef8bd00219`.
Narrow correction SHA-256:
`c3db7f69c70dcc74ba143ad36dfc0a530157d792e1ef69e15c5cbe005a2a9fa4`.
The root verified all thirteen current review pins, all 36 unchanged project
files and all 103 retained first-attempt files before authorizing one explicit
`--attempt 2` AVR invocation with the same pinned toolchain. No native rerun,
target execution or further retry is included in that authorization.
