# Finite I/O timing and static case planning candidate

This isolated candidate adds `hms/pat_io_contracts.py` and 31 original pure test
methods. All 155 inherited project files remain byte-identical to resolver
candidate03. It implements the static timing and matrix portion of the retained
[design](references/0-DESIGN.md), not its worker or independent outcome reducer.

`IoSequencePolicy` validates the complete trusted installation during construction,
including source pins. Its subsequent `qualify`, `generate_cases` and
`matrix_digest` methods operate on bounded snapshots without files, clocks,
databases or provider calls. Whole declared domains and exact installed semantics
are checked before applicability. The explicit zero-latency virtual policy checks
sequential start/completion windows and leases held during a delayed start.
Its lease enclosure deliberately overapproximates parameter correlations.

Static matrices preserve sparse enums and typed negative inputs. They carry no
qualification claim and include no fault trials. A future worker must add the
required faults/challenges and check combined case/effect budgets before running.
The existing fan profile and all source identities remain unchanged except that
the conservative I/O provider source digest includes the added HMS module.
The compiler's optional-dependency identity gap is not repaired here.

Planned selection: 31 new methods plus the existing 34 pure compiler/unit methods;
the Runtime execution method remains excluded. Candidate preparation performs
source/AST/hash checks only. Execution evidence, if produced, is retained separately
and does not change this frozen preparation record. No live integration, public
service, driver lifecycle, model, MCU or physical execution is included.
