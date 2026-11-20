# Preserved first clock semantic run

[All33 methods ran](attempt/output.log) in79.766 test seconds and104.997 elapsed
seconds. Two positive delayed-start cases errored and one unused-context assertion
failed. The four wall/mapping recovery cases and all other methods passed.

The board fold's new cause lookup used `key`, shadowing its existing
`(operation,sequence)` receipt key. It inserted the receipt under the cause key,
then rejected the resulting inventory mismatch. The
[fresh source02 correction](../../receipt-key-correction.patch) renames only this
temporary variable; predicates, evidence, tests and fixtures are unchanged.

The [acquisition proof](proof.json) retains the complete8,056-file attempt and
original empty raw root. All727 actual origins match,227 bytecode reads were
refused, and source/compiler/driver inputs remained stable. No SQLite connection,
physical execution or qualification occurred. Source01 and this failure are retained.
