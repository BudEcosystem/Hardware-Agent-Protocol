# LTO profile plan

Preserve the exact current C source, 13-case native controls, closed wire contract and complete finite/standing/runtime composition. The original target remains ATmega328P at declared 16 MHz, 2048 bytes SRAM, 32768 physical flash and 32256 application flash. The 128-byte standing state, 32-byte glue allowance, 256-byte arena, 64-byte protection reservation and 512-byte stack reservation with existing ISR/callback allowances remain.

The only executable-source change is the runner's explicit LTO build/retention/evidence profile. Parent source review precedes any invocation. Any compile, resource, diagnostic, ownership or link refusal must retain its attempt, exact input copies and logs. The runner keeps the same process limits and orderly-cleanup scope; no target or emulator execution is planned.

The final build must retain all required API/vector symbols and nine charged objects at their exact original sizes in nonoverlapping physical SRAM ranges. This is a stronger explicit linker-root policy: 26 previously present function symbols and nine previously present storage symbols are newly forced, in addition to the three prior forced function roots. No previously-unlinked helper is added. Any size comparison must disclose that policy change as well as LTO.

Fat objects provide conventional per-unit assembly/stack reports for comparison only. Save actual link/backend intermediates, IPA cgraph/inline dumps, final map, symbols and disassembly. Join every retained final function, indirect callback, library helper and ISR path to final stack evidence before deriving a bound. GCC 7.3 documentation does not guarantee complete AVR post-LTO `.su` coverage; absence or unresolved coverage remains unqualified. A smaller image is not runtime-fit proof.
