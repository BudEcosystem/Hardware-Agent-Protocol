# Standing endpoint fit candidate

Status: isolated source candidate; not compiled or tested. The sealed parent passed native controls but exceeded physical ATmega328P flash by 10878 bytes and its proposed static-growth allowance by 8 bytes. This candidate uses explicit primitive-descriptor field stores, a sufficient signed 32-bit demand-improvement difference, and byte comparisons at four sites that compare two encoded unsigned timestamps. No target fit is claimed.

The complete standing lifecycle, common finite authority, exact wire bytes, drivers, clock/boot/EEPROM/UART integration and original reservations remain. One additional native control checks signed improvement at the valid positive boundary and in the negative direction through feedback timeout and loss settlement.

| File | Purpose |
| --- | --- |
| [SOURCE-FINDINGS.md](SOURCE-FINDINGS.md) | Source/map attribution and generated descriptor evidence |
| [PLAN.md](PLAN.md) | Unchanged target, bounded delta and validation scope |
| [REVIEW.md](REVIEW.md) | Equivalence proof and new control timeline |
| [ENCODED-TIME-REVIEW.md](ENCODED-TIME-REVIEW.md) | Proof and exact scope of the four byte comparisons |
| [parent-revalidation.json](parent-revalidation.json) and [parent-index.json](parent-index.json) | Exact sealed-parent verification |
| [source-pins.json](source-pins.json), `originals/` and [project-source-diff.patch](project-source-diff.patch) | Required original copies and exact candidate delta |
| [project-source-review.json](project-source-review.json) | Current source hashes and execution status |
| [WIRE.md](WIRE.md) and [wire-vectors.json](wire-vectors.json) | Unchanged closed profile and independent vectors |
| [RUNNER-REVIEW.md](RUNNER-REVIEW.md) and [run_checks.py](run_checks.py) | Previously reviewed runner with only expected native case count updated |

The synthetic driver supplies simulation evidence only. Host durable deployment/PAT/learning integration and physical commissioning remain outside this source change. The sealed parent and public project files are unchanged.
