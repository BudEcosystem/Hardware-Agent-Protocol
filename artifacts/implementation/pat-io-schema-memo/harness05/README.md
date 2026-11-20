# Bounded remaining-cost profile

The same [cutoff test](targets.json), [source](../implementation01/README.md) and
[scope](SCOPE.md) apply. A previously reviewed standard-library cProfile wrapper
retains the top100 cumulative/self-time rows after imports. Instrumentation
changes elapsed time; this is diagnosis, not another distinct passing method.
