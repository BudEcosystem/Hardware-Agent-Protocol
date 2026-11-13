# GCC 7.3.0 compiler-option source review

This packet retains two official manual chapters, their complete readable body text, acquisition metadata and a full-text reading ledger. It supports review of a possible later LTO profile; it does not authorize flags, establish an AVR build result, or qualify target execution.

| Evidence | Scope |
| --- | --- |
| [acquisition.json](acquisition.json) | Exact URLs, HTTP response metadata, byte limits, timestamps and raw/extracted SHA-256 pins |
| [acquire.py](acquire.py) | Two fixed HTTPS requests; redirects rejected; 1 MiB response cap each; 20-second socket timeout; exclusive output creation |
| [Optimize-Options.txt](Optimize-Options.txt) | Entire extracted chapter body, 2,684 nonempty lines |
| [Developer-Options.txt](Developer-Options.txt) | Entire extracted chapter body, 754 nonempty lines |
| [reading-ledger.json](reading-ledger.json) | Exact contiguous read ranges and range hashes; no truncated reading output |
| [NOTES.md](NOTES.md) | Documented requirements, project-specific inferences and unresolved AVR evidence |

The extraction preserves all body text in document order, including examples and option tables. It decodes character references and normalizes whitespace; it is not a relevance-filtered excerpt. The raw HTML files preserve markup and links. Reading coverage means the entire extracted body, not every markup byte, the whole GCC manual, GCC implementation source, or the complete installed toolchain. Linked chapters and websites were not acquired or read in this packet.

Activity was limited to HTTPS acquisition, inert text extraction/reading, hashing and notes. No compiler, linker, object-inspection tool, candidate program, native control, emulator or target image was executed. No sealed packet was changed.
