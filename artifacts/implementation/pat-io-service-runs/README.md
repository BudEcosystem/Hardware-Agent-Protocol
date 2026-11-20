# Durable logical I/O run reservations

[Design](DESIGN.md), [results](results/README.md), [frozen source](implementation01/README.md), [exact summary](RESULTS.json), [next work](NEXT.md).

276 of 279 distinct methods pass. All 267 controls pass; the new reserved-worker method reaches its original deadline in two retained attempts, and two inherited owner-loss methods fail after supervisor or worker time limits. Their later replay assertions are unreached. The implementation remains isolated and the full HMS goal remains active.
