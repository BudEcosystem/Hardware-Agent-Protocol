# Standing endpoint: phase-size proposal

This is an unimplemented source/data proposal for the original ATmega328P profile. The sealed shared-kernel image still fails to link: 39,902 charged flash bytes, 7,134 over physical flash and 7,646 over the unchanged 32,256-byte application allowance. Its native controls passed; that does not establish target fit or a complete stack bound.

The next candidate should replace full-width numeric marshalling with byte-oriented private predicates and consolidate contiguous validation/accounting phases across finite admission, standing handling and standing polling. It must retain the full uint64 domain, existing public and driver ABI, all 29 retained function roots plus main, all nine storage roots, services and reserves. No C changes, runner, compiler invocation or target execution are included here. Expected savings are unknown.

| Record | Purpose |
|---|---|
| [ANALYSIS.md](ANALYSIS.md) | Whole-image accounting, actual generated costs, inlining and alias limits |
| [PROPOSAL.md](PROPOSAL.md) | One coordinated implementation boundary and its measurement gates |
| [SEMANTICS.md](SEMANTICS.md) | Full-width arithmetic, capture, alias, callback and failure-order obligations |
| [CONTROLS.md](CONTROLS.md) | Required differential, boundary and generated-code evidence |
| [SOURCE-COVERAGE.md](SOURCE-COVERAGE.md) | Exact reading and automated-data scope |
| [measure.py](measure.py) | Reviewed stdlib reader of frozen text/bytes; executed once by root |
| [measurements.json](measurements.json) | All 151 allocated text sections and 131 generated bodies |
| [coverage.json](coverage.json) | Reproducible coverage metadata from that reader |
| [inputs.json](inputs.json) | Twenty exact point-in-time input copies and original hashes |

Parent implementation index SHA-256: `0a4a518555e08415a9d893bba106616323a3f1a237b61bf0bc171ee8f2979909`. Prior design index: `570f0d5e84d268d88f4a3ad50df21e6fe1f293d64adc41a0d0fc66eed35191d2`. All parent inputs remain unchanged. The data reader validates these copied bytes against the originals; it does not re-execute or universally verify the parent implementation.

There is no evidence that this proposal will remove the entire remaining gap. It makes the larger next refactor actionable and measures all charged consequences. A later failed link remains an unsupported-fit result, without changing the board, domain, services, roots or budgets.
