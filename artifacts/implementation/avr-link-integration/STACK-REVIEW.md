# Combined AVR static resource assessment

The exact linked ATmega328P image passes the retained arithmetic capacity scenario. This is a static bound for the synthetic installed callbacks and actual linked clock/boot/EEPROM/RX/TX adapters. It is not measured stack usage, target execution, board commissioning or runtime-fit proof.

The parent reviewed and ran [analyze_combined_stack.py](analyze_combined_stack.py) against [AVR attempt 02](checks-avr-attempt-2.json). The complete reproducible result is [combined-stack-analysis.json](combined-stack-analysis.json), including input hashes, linked call graph, compiler frame records, indirect-call sites, maximum paths and assumptions. The ELF SHA-256 is `ad34a586b0a92c001ab02f9d3ceed70b09f43e73b17f65c01ce3d428c2b897c5`. The analysis input hashes remained unchanged.

| Item | Exact image / planning value | Limit or remaining allowance |
| --- | ---: | ---: |
| Flash, `.text + .data` | 21,778 bytes | 32,256 UNO application bytes |
| Static SRAM, `.data + .bss` | 1,343 bytes | 2,048 total SRAM bytes |
| Reserved stack | 512 bytes | Preserved prior reservation |
| Static SRAM plus reserved stack | 1,855 bytes | 193 bytes unassigned |
| Steady foreground conservative bound | 295 bytes | Exact linked callback graph |
| Startup conservative bound, interrupts disabled | 149 bytes | Exact linked startup graph |
| Timer1 overflow ISR conservative bound | 38 bytes | Non-nesting assumption |
| USART RX ISR conservative bound | 27 bytes | Non-nesting assumption |
| Foreground plus maximum computed ISR bound | 333 bytes | Excludes growth allowances |
| Retained ISR planning allowance | 64 bytes | Not reduced to computed 38 |
| Future callback growth allowance | 128 bytes | Preserved prior allowance |
| Planning stack requirement | 487 bytes | 25 bytes remain within 512 |

The planning equation is `max(149, 295 + max(64, 38)) + 128 = 487`. Both the maximum-stack constraint and the combined flash/static/stack arithmetic constraints pass. Physical flash remains 32,768 bytes; the 32,256-byte application cap reserves 512 bytes for the UNO bootloader. EEPROM remains 1,024 bytes. The target was not enlarged.

Static allocations include the complete 962-byte runtime object, 17-byte primitive callback configuration, 17-byte installation configuration, one initialized flag, the 50-byte synthetic fixture plus its 206-byte reserve (full 256-byte primitive allowance), and the unchanged 64-byte protection-service reservation. Remaining `.data` contains linked constants/initializers. The protection reservation is memory accounting only, not an implemented independent stop service. UART transmit uses the existing link response buffer; it adds no second ring.

The maximal foreground path is:

```
main → hms_avr_runtime_step → hms_endpoint_link_accept_ready
→ hms_endpoint_handle → endpoint.sample_clock → runtime.clock_snapshot
→ hms_avr_clock_read → running_config → source_config
```

Its frame maxima sum to 277 bytes, with eight extra two-byte call margins and a two-byte startup margin, giving 295. The initial manual estimate of 291 omitted the deeper `running_config → source_config` path; the complete graph found and charged it. Startup's maximal path is `main → hms_avr_runtime_start → clock_snapshot → clock_read → running_config → source_config`, giving 149 including main/call/startup margins. Disassembly places the sole `SEI` after startup returns. EEPROM boot reservation runs before Timer1 startup; it is included in the startup graph even though it is not the maximum path.

The USART RX path is `__vector_18 → runtime_receive_irq → uart_receive`. The Timer1 path is `__vector_13 → runtime_overflow_irq → clock_overflow → running_config → source_config`. Each vector pushes 15 software register bytes, and its GCC `.su` record of 17 already includes the two-byte hardware return address. The analyzer additionally charges two bytes to each ISR as a conservative margin; 27 and 38 therefore overcount that return address deliberately. The JSON field named `actual_max_non_nested_isr_bytes` means the computed conservative bound for the actual linked ISR implementation, not measured stack consumption. The independent [generated USART/ISR review](GENERATED-USART-ISR-REVIEW.md) checks SREG restoration and the non-nesting basis.

The analyzer resolves all 17 indirect sites through the installed endpoint, runtime, boot-storage and pre-feed callback mappings. It charges every reviewed possible target for a function's indirect sites, which can overestimate. It inspects the 11 referenced arithmetic/memory helper bodies for absence of stack adjustment or calls and rejects external helper branches, unknown dispatch, unbounded compiler records and recursion. The newly linked unsigned division helper has only internal loops and no stack adjustment or calls. The 64-bit shift companion symbol that only falls through is not a called root; the referenced `__lshrdi3` entry is separately bounded.

Legacy feed and RX wrappers and the USART drain API remain linked. Their conservative API-subtree bounds are 282, 87 and 11 bytes respectively, before any new caller frame. The 87-byte legacy RX wrapper bound deliberately includes the hook's possible callback even though that wrapper passes NULL. These retained APIs are not substituted into the actual runtime path to understate its stack. The synthetic fixture's old clock callback remains linked but is not called by the runtime, which installs its actual Timer1 snapshot instead.

Assumptions remain material: exact compiler/options and sources; fixed synthetic callbacks; no recursion or reentry; only the two specified non-nesting interrupt handlers; exclusive peripheral ownership; and trusted callbacks enforcing supplied limits at the I/O boundary. The bound sums each full caller maximum with its full callee maximum and adds return margins even where GCC already includes them. It does not establish execution time, interrupt blackout, Timer1 overflow service, RX queue latency, electrical baud tolerance, oscillator accuracy, EEPROM power-loss behavior, independent physical stop or actuator/sensor behavior. New standing-app state, physical drivers, callbacks or interrupts require a new combined analysis and commissioning evidence.
