# Measured costs and their limits

The retained failed-link map allocates `.text` 39,876, `.data` 26, `.bss` 1,477 and `.noinit` 0. Thus charged flash is 39,902 and static SRAM is 1,503. The exact 160-byte static delta over 1,343 remains occupied. Adding the unchanged 512-byte stack reservation gives 2,015, leaving only 33 bytes arithmetically; this is not a proof that stack fits. There is no valid linked ELF.

The reader joins every one of 151 nonzero allocated text input sections into a contiguous, nonoverlapping 39,876-byte region. It joins instruction/table widths for all 131 emitted function bodies to their map sections and backend `.su` owner rows. Their bodies sum to 39,322; the remaining startup/vector/library sections sum to 554. Data adds 26. These are disjoint charged quantities.

| Emitted owner | Body bytes |
|---|---:|
| standing.c | 15,726 |
| endpoint.c | 10,002 |
| endpoint_kernel.c | 2,348 |
| avr_runtime.c | 4,668 |
| standing_fixture.c | 3,120 |
| link.c | 1,712 |
| Remaining emitted owners | 1,746 |
| All emitted bodies | 39,322 |

An emitted owner includes its inlined descendants. For example, runtime ownership includes boot and clock work; it is not a measurement of runtime.c's original statements alone. Source ownership is neither duplication nor removable cost. An earlier informal subtotal for remaining owners was 1,450; the correct disjoint subtotal is 1,746, as emitted by the retained measurements.

The largest relevant bodies are `poll_finite` 2,190; `hms_avr_runtime_start` 2,148; `mutation` 1,872; `hms_standing_handle` 1,870; `evaluate` 1,808; fixture `standing_step` 1,762; `open_record` 1,688; `handle_finite` 1,640; `admit` 1,556; `loss_service` 1,402; and `hms_standing_poll` 1,370. `clock_snapshot` is 808 and `hms_endpoint_init` 600. The fixture remains required and charged; none of these bodies is disposable merely because it is large.

## Numeric helpers and their callers

All 19 shared-kernel bodies are single allocations without observed clones, totaling 2,348 bytes. The complete instruction views of `hms_ep_time_cmp` and `hms_ep_elapsed_cmp` show what the first extraction did not remove:

| Body | Bytes | Observed generated work |
|---|---:|---|
| time_cmp | 198 | 18 register saves, six local bytes, full operand loads/spills, two `__cmpdi2` calls |
| elapsed_cmp | 230 | 18 saves, five local bytes, full subtraction via `__subdi3`, bound construction, two `__cmpdi2` calls |
| add_room_cmp | 156 | Full operand and UINT64_MAX-minus-delta construction, two `__cmpdi2` calls |

This establishes real wide-value construction and stack traffic in predicates returning only a three-way result. It does not establish the byte-loop alternative's emitted size. Across the complete assembly there are 676 direct `call` sites, 2,037 `movw`, 617 `mov`, 1,188 `push`, 1,090 `pop`, 1,901 `ldd` and 1,114 `std` instructions. These counts include necessary state and ABI work; they are not removable-byte estimates. `rcall .` stack allocation is distinct from a call to a function.

The caller evidence matters as much as the helper bodies:

- `admit` has four `read64` calls whose results are each stored to eight local bytes before `describe`. Those 32 captured bytes cannot be replaced by later request reads. It also has ten `time_cmp` and three `elapsed_cmp` static sites. The finite admission time group repeatedly sets up addresses for related predicates; post-guard checks are a separate group.
- Standing poll inlines observation acceptance. Its generated acquisition path captures `acquired` into overlapping register/local representations and stores the captured value before report-kind checks. The two channel branches contain the same five instruction tokens setting up `hms_ep_commit_observation` at 24,468–24,472 and 24,585–24,589, each 12 bytes. That small exact repeat alone cannot justify a large savings claim.
- `evaluate` includes transition and cutoff construction. `loss_service` includes full-width duration accounting and strict witness-time checks. These paths mix callback boundaries, identity commits and pure numeric work; only the pure contiguous phases may be regrouped.

Even a physically impossible free removal of all 2,348 kernel bytes would leave 4,786 physical and 5,298 application excess. The 554 other text bytes cannot close the gap either. A useful next increment must also reduce caller work in the 28,076-byte finite/standing/kernel group; improving a single serializer is insufficient.

## Retention, inlining and runtime startup

The final WPA symbol table contains ten inline copies of retained public roots: `endpoint_refresh` three, `endpoint_fresh_clock` three, `standing_finite_slot` two, `standing_attach` one and `link_set_receive_budget` one. Weighting each copy by its present standalone body's size yields 224 bytes. This is a scale reference only: inlined transformations, call replacement and live ranges differ, so it is neither a savings estimate nor a mathematical savings bound. The attach wrapper is only 32 bytes and calls its separate 352-byte part.

Startup's actual assembly explicitly calls `hms_endpoint_init` and `hms_endpoint_link_init`; it does not duplicate the whole 600-byte endpoint initializer. WPA shows clock/UART/EEPROM/USART setup and boot-acquisition APIs inlined into startup. Those APIs are not among the 29 forced roots, and their large work is not separately retained as an additional public copy in this image. The 2,148-byte startup body therefore contains substantial unique required work. A deliberate startup phase boundary may alter register pressure, but no large duplicate removal has been demonstrated. WPA's estimates and `net +0` are compiler units, not flash bytes.

It remains valid to review selective noinline boundaries beyond the existing kernel. This evidence rules out blanket attribution of startup to duplicate retained bodies, not the possibility of a better generated boundary. The proposed main increment concentrates on demonstrated numeric/caller costs; it does not remove boot, clock, UART, EEPROM or required fixture services.

## Shared aliases and whole-image charges

Generated aliases show link `write64` and fixture `hms_st_fixture_write64` sharing `hms_ep_write64`; their write32 counterparts share `hms_ep_write32`. Fixture `read32` also shares a non-kernel `read32`, and `constants` shares `constant_copy`. Rewriting one serializer can split identical-code folding and materialize other old bodies. The proposed increment leaves the existing scalar read/write leaves unchanged. Every later map must still account for any alias split, new library helper, clone, table, trampoline, register-save routine and call site; a local body reduction is not the whole-image result.

No complete instruction-level semantics audit or combined foreground/callback/ISR stack proof is claimed here. Manual ranges and complete-source reads are recorded separately from automated enumeration in SOURCE-COVERAGE.md.
