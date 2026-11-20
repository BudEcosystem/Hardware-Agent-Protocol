# Remaining work after the stopped prefix

1. Preserve the original failed 30-second mutation profile as failed. Do not
   continue the five unexecuted profiles or reuse an attempt directory without
   a new reviewed execution plan. The 18 completed cases and their 258 checks are
   useful partial evidence; they establish neither 128-record capacity nor the
   complete 24-case matrix. Keep the 68 original settled identities, all three
   claims and the failed cleanup evidence intact.

2. Design a distinct staged capacity workload before implementing it. A concrete
   initial proposal for one deployment is at most 36 fixed owner steps, with at
   most four new original mutation identities per accumulation step. Every owner
   step would retain the existing 5CPU/256MiB child profile and a 30-second observed
   wall bound. The living guardian would have an explicit 1120-second total
   lifetime bound: at most 1080 seconds for 36 steps plus 32 seconds of setup and
   eight seconds of settlement. Its own30CPU/512MiB and the native peer's lifetime
   5CPU/256MiB limits would remain explicit. These numbers are proposed ceilings,
   not observed fit or a change to this packet's failed profile. Root must review
   the complete source and aggregate limits before any execution.

   The proposal must also bound the whole workload's storage and evidence, for
   example 256MiB total including at most 32MiB each for the main DB and rollback
   journal, at most 4MiB of retained logs/receipts/canonical deltas per step, and
   bounded frozen inputs and stream evidence within the remaining 48MiB. A
   concrete implementation must account every file and cap its count; it cannot
   silently retain an unbounded full-DB copy after each step. Any sampled disk
   monitor must remain labelled observational, not an atomic quota. With one
   supervising launcher, one guardian, one persistent native peer and at most
   36 owner steps, the proposal permits at most 39 process identities and four
   concurrently live processes. Including a separate 30CPU launcher, configured
   CPU ceilings sum to at most 245 seconds (30+30+5+36×5). These are finite workload
   accounting limits, not protected aggregate capacity or a demonstrated fit.

   A single guardian must retain the actual native peer and parent-held stream
   descriptors across owner steps. Each step opens the original authority DB,
   joins the incremented owner epoch and exact original installation/peer/boot,
   performs explicit read-only recovery, and admits only new original keys when
   existing uncertainty permits it. No fake SQL prefill, endpoint reset, changed
   key, uncertain-send retry or mutable prior receipt may bridge a step. Retain
   each step's before/after canonical changes and original bytes so the final
   audit can join the entire history. Stop at the first failed step. A pass of
   this new multi-step workload would not be a pass of the old single-process
   30-second test.

3. Consider a separately reviewed production optimization before choosing the
   staged design. The interrupted source path repeatedly scans and decodes
   retained mutation documents in`pending()`. A bounded bulk read or a validated
   transaction-local snapshot could reduce repeated work, but must preserve all
   canonical, wire-identity, original-key, corruption and uncertainty checks for
   every retained record. It must not skip settled history merely to pass a time
   bound. Any production change needs an exact semantic review and appropriate
   new qualification; the existing pass cannot be assumed to cover it. No such
   change or profiling execution has been performed in this packet.

4. Complete the unexecuted episode, activation/version, retained-owner,
   fixed-partition/metadata and charge-model controls under their reviewed bounds.
   Keep actual public-writer records separate from the in-memory charge model.
   A separate plan is still required to reach all simultaneously legal histories
   across 16 standing and 16 finite owners. It must account the whole guardian
   lifetime, registration count, aggregate storage, step count and original-key
   continuity; one-owner/per-edge results cannot stand in for that gate.

5. Complete remaining compound storage/clock-floor/COMMIT, partial-frame and
   power-loss qualification separately. Preserve the distinction between the
   passing synchronous exception controls, prior committed-boundary owner deaths
   and actual protected storage durability. Neither logical SQLite accounting nor
   owned cleanup reserves filesystem capacity, aggregate compute or universal
   descendant containment.

6. Continue toward the user's full application system: a reviewed public runtime
   mount, commissioned device/driver/hub transport on a supported endpoint,
   physical acquisition/output and loss/quiescence evidence, and broader original
   evaluation/publication of natural-language-generated PAT domains. The present
   exact synthetic domain does not qualify arbitrary learned behavior, Arduino
   hardware, driver/service replacement, GB10 or GPU readiness.

The current [data audit](AUDIT.json) and its [original source](audit_retained.py)
remain evidence for the stopped prefix only. No candidate, auditor or qualifier
was rerun during these documentation updates.
