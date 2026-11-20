# Standing endpoint LTO candidate

Status: the first attempt stopped after nine compiler-driver queries, before compilation, because a plugin file-name query used the wrong search contract. The source-grounded runner correction is prepared for review and has not been executed. All 36 project files remain exact copies of the sealed fit candidate; its 13 standing controls passed in plain and sanitizer builds, but its AVR image exceeded physical flash by 10296 bytes. This lane has run no C compilation, native probe, LTO backend, plugin or target.

The proposed profile applies matching size/LTO options at compilation and GCC-driver linking, explicitly limits LTO to one job and one partition, pins the installed backend/plugin/make inputs, and retains required API/vector symbols and charged storage. It does not imply that the image will fit or that final stack evidence will be complete.

| Evidence | Purpose |
| --- | --- |
| [PROFILE.md](PROFILE.md) | Exact compiler/link, process, retention and evidence contract |
| [PLAN.md](PLAN.md) and [REVIEW.md](REVIEW.md) | Scope, unchanged limits and source review |
| [RUNNER-REVIEW.md](RUNNER-REVIEW.md) and [runner-diff.patch](runner-diff.patch) | Changes to the previously reviewed owned runner |
| [ATTEMPT01-REVIEW.md](ATTEMPT01-REVIEW.md) and [AUDIT-ATTEMPT-1.json](AUDIT-ATTEMPT-1.json) | Preserved query-contract refusal and independent audit |
| [PLUGIN-LOOKUP-REVIEW.md](PLUGIN-LOOKUP-REVIEW.md) and [runner-attempt1-diff.patch](runner-attempt1-diff.patch) | Source-grounded correction; no retry yet |
| [retention.json](retention.json) | All 29 function roots and nine exact storage roots, joined to the parent map |
| [toolchain-pins.json](toolchain-pins.json) | Archive-derived tools, LTO backend/plugin, specs and host make/shell pins |
| [parent-revalidation.json](parent-revalidation.json) | Revalidated fit and compiler-review seals |
| [source-pins.json](source-pins.json), `originals/`, [project-source-review.json](project-source-review.json) | Exact source identity; empty project source diff |
| [WIRE.md](WIRE.md) and [wire-vectors.json](wire-vectors.json) | Unchanged standing profile and independent vectors |

Per-unit fat-object `.su` data is explicitly pre-LTO. Final disassembly, backend artifacts, IPA information and complete callback/ISR accounting must establish the actual linked stack separately. Missing coverage leaves stack fit unqualified, even if flash and static arithmetic fit. No physical driver, commissioning or complete durable-host/PAT integration is supplied by this profile.
