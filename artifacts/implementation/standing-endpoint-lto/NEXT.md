# Remaining fit work

Keep the original ATmega328P limits and full endpoint/standing/runtime contract. LTO reduced the failed-map flash total but leaves 9124 physical bytes, or 9636 application bytes, to remove. The current profile is unsupported on that target; its SRAM reservation arithmetic does not repair the flash failure or establish stack fit.

The next concrete investigation is a source-and-artifact comparison of the retained WPA/LTRANS decisions and backend assembly against the parent map, concentrating on the large standing poll/handle and finite endpoint poll/handle bodies. Attribute repeated wide-value work, serialization and inlining before proposing a bounded refactor. Preserve the explicit API/vector roots, ordinary-versus-loss authority checks, lifecycle/ACK semantics, charged storage and all current native controls. No new compiler option or source edit has been applied after this result.

The possible backend `.su` is useful evidence for later analysis, but a complete linked foreground/callback/helper/ISR graph and exact generated UART boundary review remain necessary if a future candidate links. The 512-byte reservation cannot be justified by importing the old finite bound or summing pre-LTO frames.

The [plugin lookup research](../../../research/constrained/avr/plugin-lookup-review/README.md) is sealed separately. Both attempted builds and their refusal evidence remain intact. Physical driver commissioning and durable hub/PAT integration remain outside this compiler-profile increment; the work above is unexecuted follow-up.
