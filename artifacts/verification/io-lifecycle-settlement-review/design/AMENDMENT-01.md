# Preserve administrative invalidation during historical settlement

This parent-approved design correction supplements, and does not replace, the frozen `DESIGN.md` (SHA-256 `f37bd842c94a72c30abc05e1f841e44f9f37a55bb21956cf7802f6716d00732c`) and original `index.json`. No code or test was changed or executed.

The existing Registry `_bind_in_tx` writes a new `reg_bindings` row with `active=1`. Reusing that publication behavior without qualification would re-enable an affected consumer that an administrator invalidated after the synthetic generation effect and before authority settlement. A proved historical effect must not grant fresh execution authority.

The proposed transaction-internal lifecycle binding plan therefore captures and preserves each affected binding's **current** `active` value under the authority transaction. It permits publishing the exact derived generation/proof while keeping an invalidated binding inactive. Current active/inactive status is not taken from the old dispatch snapshot or provider receipt. No public parameter chooses an activation value, and the submitting operation principal supplies no replacement administrator Context. The public admin bind method retains its current explicit activation behavior.

The common internal binding validation/apply extraction must separate this settlement-only state-preservation rule from ordinary administrative activation, without weakening description, route, resource/action-envelope, history/non-reuse or same-instance claim checks. A validated internal settlement plan carries the preserved value; arbitrary caller-constructed plans are not an exposed interface. This is a trusted in-process boundary, not a Python sandbox.

Scoped rebase still requires exact current binding document/proof/dependency identity. A change in the separate active flag alone does not justify abandoning the already evidenced effect, and does not permit the settlement to set that flag back to true. Neither the generation publication nor evidence reconciliation modifies grants. Journal truth recording and resource release remain governed by exact receipt/current-board/claim validation.

The pinned Registry also has a `reg_instances.retired` storage column, displays it, and denies fresh work when it is set. There is no retirement mutation API identified in these selected sources. Settlement must leave that existing column unchanged; this amendment does not invent a retirement workflow or claim to test one.

Required original integration regressions: commit the provider effect, invalidate one affected binding, then settle/reopen. The new token and proof are retained, claims release only with exact safe-idle evidence, the binding stays inactive, and fresh invocation still refuses. Also revoke the submitting user's grant before settlement and verify historical truth can be recorded without restoring the grant. A missing/rebound binding, changed document/proof/dependency or inconsistent board still refuses with claims retained. Public administrative bind activation must retain its previous behavior.

The correction is design only. It does not establish physical restart safety, live lifecycle support, an implemented settlement capability or completed public mounting.
