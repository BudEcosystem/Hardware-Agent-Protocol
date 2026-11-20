# AVR attempt1: retained integer-promotion refusal

After native attempt2 passed, root invoked the first AVR stage against the retained pinned toolchain. The stage stopped while compiling `standing.c`: three bounded ring-index additions promoted byte operands to signed `int` on AVR before applying unsigned `&1u`, and `-Wsign-conversion -Werror` refused them. No complete standing ELF was linked or executed.

The only subsequent source correction is an explicit `unsigned` conversion of the head byte before each of those three additions. Head/count/loop values and ring selection remain bounded and unchanged. Warnings, flags, target and budgets remain intact. Root review precedes native attempt3 and AVR attempt2; no independent invocation occurred during this correction.

`checks-avr.json`, `build/avr/` and both existing native attempts remain untouched. Prior source review/diff copies are under `review-history/avr-attempt-1-*`. The AVR attempt reports all original/frozen source, runtime and installed tool pins stable; owner empty/closed; no cleanup errors/pending interrupts; all observed command groups absent. Nine outer commands were reaped.
