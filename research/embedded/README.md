# Embedded source review

The result is [embedded-evidence.md](../../docs/embedded-evidence.md). This lane inspects concrete MCU command, scheduler, motion and rclc executor implementations. It does not establish a working HMS firmware, timing guarantee or physical-device result.

- [repositories.json](repositories.json) records exact URLs and commits, root-relative retained paths, acquisition method, and the specifically inspected files.
- [reading-log.json](reading-log.json) records SHA-256, exact byte/LF counts and inclusive reading coverage for 35 complete files (11,542 logical lines). These are selected files across four checkouts; no entire-repository reading claim is made.
- `repos/configurable-firmata/` is an unmodified depth-one checkout of the official `firmata/ConfigurableFirmata` repository at `3734757348263e890d276f7e4fbc1f7e2bf5f2b9`. Its URL was obtained from the already retained official Firmata protocol's implementation links. No submodules or dependencies were fetched.
- The other three checkouts remain under `research/protocols/repos/`. Their earlier manifests were not changed. This log adds complete-file coverage for StandardFirmata, the rclc executor and the dependencies expressly listed.

Review method: read all text of listed files through `cat` and contiguous `sed` ranges, use searches only to locate definitions and references, and follow the call paths relevant to parser state, scheduling, motion and callbacks. Where a display was truncated, redisplay the affected ranges before marking the file complete. Byte hashes are over retained source, including original line endings. Read coverage is an inspection record, not proof of correctness.

No acquired third-party code was compiled, installed, run or modified. The checks below only hash files, check coverage metadata and ask Git for the pinned commit and working-tree status:

```bash
python3 research/embedded/verify.py
```

Hardware/toolchain measurements and the compact HMS serial proposal belong to separate work. The evidence document states missing dependency and physical-validation coverage explicitly.
