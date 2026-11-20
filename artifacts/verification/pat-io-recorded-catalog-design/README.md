# Original-run catalog integration review

The [compact store](../../implementation/pat-io-content-store/README.md) now passes actual bound-worker import and historical replay within the original retention limits. This review identifies the next catalog/execution changes from the frozen source. It adds no production behavior and claims no new test pass.

The existing compiler intentionally omits endpoint sessions from its static evaluation environment. The existing execution selector compares that environment before calling catalog eligibility. Consequently, changing only the catalog environment schema would make otherwise applicable candidates disappear before the new checks ran. An integration must preserve the compiler's static environment representation and add an explicit, separately versioned applicability contract, with selection ordering reviewed at the same time.

The [contract and acceptance plan](DESIGN.md) covers original invocation identity, historical replay, current source-device applicability, prepared semantic verification and refusal classification. [Source notes](SOURCE-NOTES.md) identify the reviewed methods; `inputs.json` pins their actual source bytes to the completed compact-store source index. This is primary-agent review, not independent review.

The full goal remains active. Device I/O, drivers and intelligence-hub resources remain within the unified authority/tool model. This finite simulation integration does not implement physical providers, persistent Arduino applications, prompt learning or hub compute/service lifecycle.
