# Standing endpoint size-reduction proposal

Source/data-only proposal against the sealed `standing-endpoint-copy-boundary` candidate. The unchanged ATmega328P image still needs **9,042 fewer bytes to reach physical flash**, and **9,554 fewer bytes to reach the retained application allowance**. No candidate source, runner or profile was changed here. No compiler, inspection binary, native control, emulator or device was executed.

The next useful increment is a coherent private time/serialization refactor across standing poll, standing handling and finite handling, followed by generated-code-selected phase boundaries. Another isolated copy substitution is insufficient evidence for the remaining gap. The proposed work preserves the public and driver ABIs, complete 64-bit time domain, both wire protocols, ownership/loss semantics, all retained roots and every charged storage object. Original-board fit remains unsupported.

| File | Purpose |
|---|---|
| [ANALYSIS.md](ANALYSIS.md) | Measured bodies, repetitions, helpers, frames and feasibility |
| [PROPOSAL.md](PROPOSAL.md) | Concrete implementation boundaries, semantic obligations and stopping criteria |
| [SEMANTICS.md](SEMANTICS.md) | Full-domain algebra, snapshot, write-order and phase equivalence rules |
| [CONTROLS.md](CONTROLS.md) | Behavioral and generated-code qualification plan; unexecuted |
| [SOURCE-COVERAGE.md](SOURCE-COVERAGE.md) | Exact evidence scope and limits |
| [source-pins.json](source-pins.json) | Original input paths, hashes and frozen small input copies |
| [measure.py](measure.py), [measurements.json](measurements.json) | Reproducible stdlib-only retained-text measurements |
| [coverage.json](coverage.json) | Exact read-range hashes; mechanical enumeration distinguished from semantic reading |
| [body-observations.json](body-observations.json) | Literal repeated instruction-token spans and direct-call sites |

The parent index is `49ae3507a68d994d0fc9454146850358b793511fa585f8e96e3f607b54e90a6c`; all 640 indexed files were revalidated before analysis. The parent's native 14-case/766-assertion standing controls passed in plain and sanitized builds. Its AVR link failed. Those are retained parent results, not runs performed in this packet. This proposal is not a fit qualification, a physical-I/O claim or completion of the host durable/PAT integration.
