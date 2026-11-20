# Remaining independent clock-history composition

The new 0.3 reader checks serialization, paired configuration, exact fixed-case
identity/program timing, source changes, calls and clock epochs. It explicitly
returns false for full history, expected outcome and qualification. Extend the
semantic folds before treating these captures as qualification evidence.

1. Derive the phase-local clock timeline from the separately trusted case and
   verified control records. A dispatch reserved at 1,000,000 can have its final
   guard at 1,000,099. Do not assign the after-clock to every event in the phase.
   Preserve source-specific wall/monotonic time and clamped audit-time semantics.
2. For start/run equality, verify the old accepted child, exact dispatch ticket,
   retained claims and original budget origin before deriving the excluded due
   time. Require a start-excluded receipt with `duration_budget_excluded`, no
   activation/fence, complete authority evidence and release, and failed parent.
3. Derive wall regression from the retained authority floor. Derive mapping
   invalidation from the prior monotonic source and retain its invalid latch
   across source restoration until a new owner epoch. The six failed-clock
   snapshots have all 29 execution and 15 configuration tables unchanged;
   output and claims remain active. A failure string alone cannot justify this.
4. A new epoch opens the same stores and preserves old identities and fences.
   In all four recovery cases the board has stopped, the authority operation is
   still `outcome_unknown`, and its claims remain held. Require the original
   receipt's `board_owner_reopened` cause and later reconciliation before release.
5. Check parent interruption, exact failed resume and cancellation, with no suffix
   admission or old-request rebinding. Preserve observation sequences and epochs:
   failed refresh publishes no new samples; reopen creates new streams.
6. Extend private cause/timing handoffs only with fully derived, exactly consumed
   evidence. Default legacy readers must continue rejecting the new profile.
   Reject rehashed hidden activations, relabeled clock failures, fake refreshes,
   early claim release, changed dispatch origins and reused owner sessions.

Full semantic composition must still feed the complete candidate matrix and group
budget reducer. These synthetic reopen stops do not establish an autonomous stop
deadline, a physical clock guarantee, driver/hub deployment qualification or a
persistent prompt-defined application.
