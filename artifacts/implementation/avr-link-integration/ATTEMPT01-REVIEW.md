# Native attempt 01: test packet correction

The root executed the reviewed native stage. `checks-native.json` and `build/native/` preserve its exact source byte copies, commands, compiler outputs and failure. The unchanged original native endpoint suite and framed pipe smoke passed. The integration plain build succeeded, then its tenth case, `finite_operation_over_wire`, failed at the expected-success assertion for a malformed QUERY. The eleventh case had not run; the new ASan integration build/run had not yet been reached.

The defect was in the test request. QUERY requires exactly 44 payload bytes: the prefix plus generation, handle, call number and the original 32-byte intent digest. The test sent only 12 bytes and incorrectly expected OK. The endpoint's refusal follows `protocol/endpoint/endpoint.c` syntax validation and `spec/11-endpoint-wire.md` QUERY layout; this is not a runtime/transport defect.

The only correction is in the source `project/tests/avr_runtime_probe.c`. The packet array now holds 44 bytes. The 12-byte QUERY remains as a negative check expecting the declared `HMS_EP_BAD_LENGTH` constant at request sequence 4; the full request then includes the original digest bytes `0x60+i` and succeeds at sequence 5. Both checks assert dispatch/effect counts remain exactly one. No production source or runner changed. No prior attempt file is modified.

The root-owned receipt reports original and copied source hashes unchanged during attempt 01, direct children reaped, and all three owned process groups absent. No AVR build had started, no target ELF was executed, and no physical port or device was accessed. The corrected source requires root review and a new explicit attempt; it has not been independently executed by this agent.

Corrected probe SHA-256: `75f5e0be885d4751660675efdfcc9815bf604f10904bb2f1a246ba47f2a7e2ac`. Failed-attempt probe SHA-256: `6d69c9b5cfa58afbc12d02aa2444fe5d391e99e07dea1de94af16d569b5e1919`.
