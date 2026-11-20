# Recorded guard delay and clock-fault candidate

The [design](../DESIGN.md) adds exact clock controls and separate wall/monotonic
recording for the three required guard/clock challenges. Runtime/provider/compiler
business logic and all old tests/data are unchanged. See [source review](source-review.json).
Full semantic clock-fault composition and qualification remain unfinished.
