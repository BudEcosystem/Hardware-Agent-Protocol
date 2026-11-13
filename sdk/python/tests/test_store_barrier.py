"""Store barrier semantics: a barrier requested inside a NORMAL transaction must still reach stable storage (BHMS-OPS-003)."""

from __future__ import annotations

from bhms.runtime.store import Store


def test_nested_barrier_in_dispatch_mode_is_promoted_not_an_error(tmp_path):
    store = Store(tmp_path / "s.db", durability="dispatch")
    try:
        with store.transaction():  # NORMAL outer transaction
            store.meta_set("a", "1")
            assert store.next_counter("fence") == 1  # nested barrier: SQLite cannot change the level mid-transaction
        assert store.meta_get("a") == "1"
        assert store.counter("fence") == 1
        assert store.execute_scalar("PRAGMA synchronous") == 2  # left at FULL by the promoted barrier
        with store.transaction():  # still usable afterwards
            store.meta_set("b", "2")
        assert store.meta_get("b") == "2"
    finally:
        store.close()


def test_nested_barrier_rolls_back_with_the_outer_transaction(tmp_path):
    store = Store(tmp_path / "s.db", durability="dispatch")
    try:
        try:
            with store.transaction():
                store.next_counter("fence")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert store.counter("fence") == 0
        with store.transaction():
            store.meta_set("c", "3")
        assert store.meta_get("c") == "3"
    finally:
        store.close()
