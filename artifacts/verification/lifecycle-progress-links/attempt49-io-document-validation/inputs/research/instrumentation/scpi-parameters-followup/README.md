# SCPI parameter and coupling follow-up

This overlay reads all of SCPI-99 Volume 1 Chapter 7: newly covered LF lines 1571–2054 and all ten PDF pages 34–43, including the logarithmic stepping formulas and the voltage/power/impedance equation. Page 43 is the blank chapter-ending page.

The [reading receipt](reading.json) adds 484 lines to the unchanged [original receipt](../reading-instrumentation.json) and [header overlay](../scpi-headers-followup/reading.json). Combined coverage is **2,780 of 42,293 LF lines**. The 819-page standard remains partially read; IEEE 488.2, later SCPI chapters and actual instrument manuals are separate work.

[Notes and binding implications](NOTES.md) cover native rounding, unspecified error effects, relative steps, numeric sentinels, coupling, units and amplitude conventions. These are proposed HMS requirements, not an implemented or qualified instrument driver. No acquired code, instrument or physical device was executed.

The [audit](audit.json) verifies source pins, exact nonoverlapping LF ranges and all ten retained image hashes; it does not prove comprehension. The [index](index.json) seals this reading overlay without rewriting earlier receipts.
