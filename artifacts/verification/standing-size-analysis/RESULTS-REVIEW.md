# Retained AVR object inspection

Nine bounded `nm`/`objdump` commands completed successfully. Their original
objects were inspected as data and never executed. The unchanged sealed runner
retained command intent/start/result records, verified source/tool/interpreter
pins and reaped all nine commands. [AUDIT.json](AUDIT.json) independently joins
those retained bytes and confirms the observed process identities are absent.

The complete `finite_describe` disassembly fragment contains an eight-byte copy
loop whose source address has both low/high `.rodata` relocations. The retained
constant bytes are `e803000003200100`: little-endian 1000 followed by resource mask
3, simulation evidence mask 32, cancellation support 1 and result length 0. This
establishes the source/layout attribution that the prior failed map alone could
only suggest.

The audit classifies every `R_AVR_CALL` relocation by its preceding `call` or
`jmp` instruction, since that relocation type covers both. Within standing poll,
the original object has 27 static calls to the 64-bit reader, 31 to `__cmpdi2`,
seven to `__subdi3` and six to `__adddi3`. These are static instruction-site
counts, not dynamic execution counts, timing, or an attribution of all surrounding
instruction bytes. Local jumps are recorded separately.

Only the descriptor fragment and constant received a complete instruction-level
review here. Relocation counting is not a complete semantic review of the large
controller functions, a combined stack analysis, or evidence that all absent
source helpers were duplicated. Many helpers have a single source call site.
The original wide arithmetic library bodies are already shared; size changes
must be measured against complete retained builds.

The subsequent [fit candidate](../../implementation/standing-endpoint-fit/RESULTS-REVIEW.md)
uses these observations with separate source equivalence proofs. Its actual
measurements belong to that packet. This inspection alone establishes no
reduction, valid target image, physical behavior or end-to-end application.
