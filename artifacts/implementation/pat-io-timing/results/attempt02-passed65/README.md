# Finite I/O timing: 65 pure checks pass

The corrected isolated run passes all 65 methods in 7.469 test seconds: 20 existing
compiler methods, 14 fixed-unit methods and 31 I/O static-contract methods. The
[earlier failed65 run](../attempt01-failed65/README.md) remains retained. Only its
enum-hole fixture changed; the production policy and other 156 project inputs
are byte-identical. The corrected method now checks both the parser refusal and
the intended empty-domain branch.

The policy checks exact GPIO/PWM semantics, complete declared duration domains,
sequential start/completion limits, early-admission leases and safe integer origin
bounds. Case planning preserves enums and bool/integral-float negative inputs,
refuses quota overflow, and agrees with actual compiler outcomes. A guarded test
checks that planning after trusted setup performs no file, clock, SQLite or
provider calls. These are actual in-process assertions, not independent execution
attestation. The interval lease rule is intentionally conservative for correlated
parameters.

All 157 project inputs, 164 frozen preparation entries, six active harness inputs
and 159 selected external pins stay stable. Compiler/provider identities match
before/after and across both attempts. All recorded origin files were rehashed.
The original private scratch root remains retained and empty.

See [proof](proof.json), [actual result](attempt/result.json), [test log](attempt/output.log),
[source candidate](../../implementation02/README.md) and [index](index.json).
No Runtime, resolver, I/O provider tick, qualification worker, model or physical
device ran. Live integration, independent outcome reduction, public qualification
and persistent prompt-defined applications remain unfinished.
