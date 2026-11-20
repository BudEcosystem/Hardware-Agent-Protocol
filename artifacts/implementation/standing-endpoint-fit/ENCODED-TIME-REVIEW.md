# Encoded timestamp comparison review

This is source-only review. Exactly the four direct comparisons below are changed in the candidate. References use the frozen parent copy [standing.c](originals/protocol/endpoint/standing.c).

For two canonical eight-byte big-endian representations of unsigned 64-bit values, lexicographic unsigned-byte order equals numerical order. The first unequal byte has higher positional weight than every following byte combined. Thus `memcmp(a,b,8)` compared with zero using the same relational operator is equivalent to comparing the two decoded values, for every bit pattern including equality, zero, the high-bit boundary and all-ones ABSENT. This uses only the standard sign guarantee of `memcmp`, not any particular return magnitude, host endianness or alignment.

| Original line | Existing relation | Encoded operands | Direct equivalent |
| --- | --- | --- | --- |
| 290 | Renewal lease <= current lease | `p+52`, `s->bytes+ST_LEASE` | `memcmp(p+52,s->bytes+ST_LEASE,8)<=0` |
| 563 | Feedback acquisition > activation dispatch | `o+OBS_AT`, `r+4` | `memcmp(o+OBS_AT,r+4,8)>0` |
| 568 | Demand acquisition > activation dispatch | `s->arena->observation[0]+OBS_AT`, `r+4` | `memcmp(s->arena->observation[0]+OBS_AT,r+4,8)>0` |
| 693 | Loss observation <= confirmed loss handoff | `report+20`, `s->bytes+ST_QUIET_AT` | `memcmp(report+20,s->bytes+ST_QUIET_AT,8)<=0` |

Both operands at each direct site are readable eight-byte fields. The comparison contains no callback or write, and the enclosing guards, short-circuit order and refusal reasons remain exactly where they were. The special lifetime of `ST_QUIET_AT` is unchanged: at the fourth site it holds the confirmed loss handoff, with the preceding ABSENT check retained.

Two further comparisons have a local decoded alias: line 535 compares `acquired` (decoded from `r+20`) with `o+OBS_AT`, and line 542 compares the old observation timestamp with that same `acquired`. No write to either source occurs before these tests, so byte comparison is also equivalent under the existing serialized/no-callback-mutation contract. They are separate data-flow changes, not part of the four direct substitutions. Other uses of `acquired` still need its numerical value.

No direct two-encoded-64-bit comparison appears in the current finite core. Its admission code has decoded locals (`nb`, `latest`, `complete`, `lease`) and later arithmetic/native time limits; these should receive a separate data-flow review if considered. Native current-time comparisons, lease-window arithmetic, saturation, conservation sums, subtraction and comparisons with constants are outside the proposed four-site substitution. Sharing a byte comparison does not justify weakening those distinct rules.

The existing image already links `memcmp`, but flash, stack and cycle effects of substitution remain empirical questions. The unchanged native lease/replay and loss-witness before/equal/after controls remain required, alongside the new signed-feedback case. These source changes have not been compiled or tested.
