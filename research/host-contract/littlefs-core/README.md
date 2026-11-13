# littlefs core suitability review

Stage 83, 2026-11-09. The pinned repository is retained locally: 69 regular files,
1,896,639 bytes, from commit `6cb4e86540eca0d9ba62500a298385c9d863c8be`.
[Acquisition](acquisition.json) records exact primary URLs, archive identity and
all file identities. The archive is 280,264 bytes with SHA-256
`4803faf6db6c60093558a315a10c50926d2cfa5668a3f03fa2523fd09b10b747`.

**Eleven selected files / 12,041 LF lines are fully read.** Nine files / 11,674
lines were newly read here: core, public and utility headers/implementation,
design, on-disk specification and three selected test sources. README and license
are byte-identical to the prior full reading. The remaining 58 repository files
are explicitly unread in [reading coverage](reading-coverage.json). This is not
a claim of full-repository or upstream-test coverage.

All design ASCII figures and encoded equations were read; the three linked
technical plots were acquired, rendered and visually inspected. Their mutable
image-branch URLs are distinct from the pinned core commit. Original SVGs,
rendered PNGs and identities are in [assets](assets/acquisition.json).

[Notes](NOTES.md) distinguish source behavior, local observations and proposed
integration. The [original RAM probe](../../../artifacts/verification/littlefs-semantics/README.md)
compiled only the fully read core and utility implementation with caller-owned
buffers. Four bounded scopes completed, showing suffix-copy costs, stale separate
handles and release-only unmount. No upstream Makefile, scripts, emulator or test
runner executed. No SQLite, FUSE mount, physical flash or power-loss trial ran.

**Decision:** do not adopt a direct file-descriptor-to-littlefs-handle provider.
The next candidate is an explicitly bounded chunked adapter with shared inode
state, whose semantics must be established before SQLite integration. littlefs
remains a candidate for immutable endpoint PAT packages. Neither use is physically
qualified. See the [provider decision](../../../artifacts/verification/littlefs-semantics/DESIGN.md).

The BSD license is retained in [LICENSE.md](repo/LICENSE.md). The source archive
and host experiment are research artifacts, not an installed runtime dependency.
