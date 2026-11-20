# Standing endpoint LTO candidate

Status: source-only compiler-profile preparation. All 36 project files are exact copies of the sealed fit candidate; its 13 standing controls passed in plain and sanitizer builds, but its AVR image exceeded physical flash by 10296 bytes. This lane has not invoked a compiler, native probe, LTO backend, plugin or target.

The proposed profile applies matching size/LTO options at compilation and GCC-driver linking, explicitly limits LTO to one job and one partition, pins the installed backend/plugin/make inputs, and retains required API/vector symbols and charged storage. It does not imply that the image will fit or that final stack evidence will be complete.

| Evidence | Purpose |
| --- | --- |
| [PROFILE.md](PROFILE.md) | Exact compiler/link, process, retention and evidence contract |
| [PLAN.md](PLAN.md) and [REVIEW.md](REVIEW.md) | Scope, unchanged limits and source review |
| [RUNNER-REVIEW.md](RUNNER-REVIEW.md) and [runner-diff.patch](runner-diff.patch) | Changes to the previously reviewed owned runner |
| [retention.json](retention.json) | All 29 function roots and nine exact storage roots, joined to the parent map |
| [toolchain-pins.json](toolchain-pins.json) | Archive-derived tools, LTO backend/plugin, specs and host make/shell pins |
| [parent-revalidation.json](parent-revalidation.json) | Revalidated fit and compiler-review seals |
| [source-pins.json](source-pins.json), `originals/`, [project-source-review.json](project-source-review.json) | Exact source identity; empty project source diff |
| [WIRE.md](WIRE.md) and [wire-vectors.json](wire-vectors.json) | Unchanged standing profile and independent vectors |

Per-unit fat-object `.su` data is explicitly pre-LTO. Final disassembly, backend artifacts, IPA information and complete callback/ISR accounting must establish the actual linked stack separately. Missing coverage leaves stack fit unqualified, even if flash and static arithmetic fit. No physical driver, commissioning or complete durable-host/PAT integration is supplied by this profile.
