# Compact availability: preserved before evidence

Four deterministic probes passed in 8.822 seconds against an isolated copy of
the original runtime. They use one SQLite simulation route and two independently
enrolled original C native fixtures, synchronized virtual wall/monotonic/endpoint
clocks, and actual SQLite transactions. No production source was changed.

`probe.json` retains exact presence rows, authority time, ready observations,
counts, clock floors, SQL commit sequence and route faults. `probe-output/`
retains SQLite snapshots before and after the relevant boundaries. `analysis.json`
contains the derived comparison and original failed-459 receipt linkage.

| Case | Exact boundary and result |
| --- | --- |
| Fresh baseline | At 100000, presence expires 101000; admission succeeds. |
| Authority-floor commit delay | Sample 100001, expiry 101001; a 1100 ms logical pause makes all three presence writes occur at 101101. Refresh returns without a fault; admission refuses `DEVICE_UNAVAILABLE`. |
| Publication commit delay | Writes occur at 100001, expiry 101001; a 1100 ms logical pause at final commit return makes admission at 101101 refuse. |
| Other route delays target | Eight commits in one healthy C1 refresh each consume 150 logical ms under the shared Journal mutex. C2 expiry 101000 is checked at 101200 and refused. An explicitly requested C2 refresh admits the unchanged request at 101200. |

Every refusal leaves operation, claim, endpoint command and exact replay-key
counts at zero. Both native fixtures report zero dispatches and effects after
refusal. The explicit recovery refresh adds one HELLO transmit/response pair,
no OP/ARM/BIND, leaves grants and bindings unchanged, and allocates nothing until
the subsequent original admission. No second native-counter read was taken
after that explicit refresh; the retained packet and database deltas support the
narrow no-handoff statement.

The delays represent logical elapsed time after real commits, including possible
scheduling delay; they are not measured filesystem latency. The contention probe
proves one blocked mutex acquisition, not general scheduler starvation. A finite
presence lifetime can expire during arbitrarily delayed persistence. The
fail-closed refusal is correct; old HELLO/ready evidence must not be restamped.

These mechanisms do not establish the cause of the historical failed 459-test
attempt. That run did not capture the exact presence row and time at each refusal.
Its later renewed row cannot establish the earlier chronology. The original
failure and earlier diagnosis remain unchanged.

`baseline-pins.json` covers the initial 59 copied inputs. A pre-discovery import
failure identified one omitted data-only WoT schema; `preflight.json` records it
and `supplemental-pins.json` pins the added dependency. All 60 copied inputs were
verified before and after the four-case run. The probe refuses existing output
directories, so this preserved run cannot silently overwrite itself.
