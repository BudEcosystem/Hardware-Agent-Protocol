# SCPI notation and program-header follow-up

This overlay adds a complete reading of Volume 1 Chapters 5 and 6 of the retained SCPI-99 specification: extracted-text lines 971–1570 and PDF pages 22–33. All twelve rendered pages were visually inspected, including the two syntax diagrams on page 24 that are missing from the extracted text. Page 33 is the blank final page of Chapter 6.

The [reading receipt](reading.json) records 600 newly covered LF-delimited lines. Together with the unchanged [earlier receipt](../reading-instrumentation.json), coverage is 2,296 of 42,293 lines. The 819-page specification remains **partially read**. Rendering a page is not counted as reading it; linked IEEE standards and instrument manuals are not covered.

[Notes and HMS implications](NOTES.md) distinguish native parser state, partial effects, query semantics, channel addressing and logical instruments. These findings constrain a future device/driver binding; they do not implement or qualify one. No instrument, acquired code or physical I/O was executed.

The [audit](audit.json) verifies source hashes, exact LF ranges, the nonoverlapping union with earlier coverage and retained image hashes. The [index](index.json) seals this overlay. It does not independently establish that a person or agent understood the source.
