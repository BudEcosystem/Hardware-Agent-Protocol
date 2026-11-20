# Next integration

Preserve this stage and all earlier failures. The public supervisor still uses
the original Python walker. No actual qualification worker ran here.

1. Define the trusted wrapper contract for the actual `tree_usage` call sites.
   Decide supported path/limit types explicitly, map the native structured result
   into existing supervisor errors, and retain the stronger opened-directory
   checks. Do not silently fall back to a weaker Python path.
2. Design production artifact loading and its platform/source/DSO identity.
   Extend supervisor image inputs and producer/consumer identity derivation to
   include the wrapper, native source and exact binary. The current evaluation
   loader assumes its input directory cannot be concurrently modified; it does
   not complete this deployment contract.
3. Update the isolated execution harness to recognize the new native event,
   authorize the exact original supervisor/attempt roots, and pin artifact origin.
   Native per-entry filesystem activity bypasses ordinary Python audit hooks.
   Retain the existing resource/effect bounds and explicit no-sandbox limitation.
4. Create a fresh isolated candidate from the frozen proof-build source and
   independently recompute identities. Execute the unchanged full 30-case
   authority-vault worker/import scope within its original 60/180-second bounds.
   Do not reduce the matrix, expand quotas, mutate failed state, retry with new
   operation keys or claim that these binding controls guarantee the deadline.
5. Continue held-snapshot catalog and immediately-before-business-commit
   validation, backed control capacity and public service integration. Prompt
   synthesis, validated learning, persistent Arduino applications and actual
   device/driver/hub providers remain separate required implementation work.

The new documentation packet is partially read: the remaining ranges and linked
sources remain in the research backlog. This stage establishes neither complete
CPython implementation review nor whole-runtime conformance. Signals during
uninterruptible filesystem stalls, non-main-thread cancellation, interpreter
shutdown, subinterpreters, other CPUs/Python versions and all possible concurrent
mutations remain unqualified.
