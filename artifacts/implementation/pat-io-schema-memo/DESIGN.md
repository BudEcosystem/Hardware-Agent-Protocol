# Reuse successful topology schema validation within a process

The retained [profile](../pat-io-group-worker/PROFILE-ANALYSIS.json) measured
repeated JSON Schema checks while a shared group failed its original60s deadline.
This candidate changes one inherited production file. It keeps the original
canonical byte and strict scalar checks, obtains a fresh parsed JSON tree on
every call, and reuses only successful JSON Schema validation for exact bytes
under the same private validator object. All graph, electrical footprint,
generation, binding and lifecycle semantics still execute on every call.

An LRU holds eight entries across profiles. Keys retain at most512KiB of bounded
document bytes, plus Python object overhead. A lock protects dictionary access;
validation runs outside it. Concurrent misses can repeat work but cannot publish
schema failure as success. Outputs and input dictionaries are never retained in
the cache. Replacing a validator object cannot inherit success from its predecessor.
Private import-time validators are not a supported mutable configuration surface;
in-place mutation of their schemas is outside this reuse contract. Compiler and
installed-source identity checks remain separate and unchanged.

Fresh selections run21 existing topology tests,11 new schema reuse regressions,
and12 existing group budget/preflight checks; the actual record cutoff and full
GPIO/PWM groups each retain a separate original bounded harness invocation. No
case, schedule, evidence field, fault, storage ceiling or deadline is removed or
increased. All prior indexed sources and failed attempts remain unchanged.
Faster capture alone cannot qualify a PAT: independent current-group outcomes,
trusted setup/run association, enforced aggregate storage and supervision remain
required. Physical device and hub lifecycle providers remain separate work.
