"""Task 7b group A: semantics found wanting by Tasks 10 and 11 (hazardous leases, reconcile on return, operator resolution)."""

from __future__ import annotations

import pytest

from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.server.decorators import DescriptionError
from bhms.server.device import Device

# ---------------------------------------------------------------------------- A5: hazardous actions require a lease


def _hazardous(**options):
    dev = Device(None, "oven-1", resources=["oven-1/heater"])

    @dev.action(effect="hazardous", idempotency="absolute", max_duration_ms=1000, **options)
    def heat(ctx) -> None:
        """Heat."""

    return dev


def test_a_hazardous_action_must_require_a_lease():  # BHMS-DEV-033 (Task 10 gap 8: the centrifuge spin ran without one)
    with pytest.raises(DescriptionError) as exc:
        _hazardous()
    assert "BHMS-DEV-033" in str(exc.value) and "requires_lease=True" in str(exc.value) and "heat" in str(exc.value)
    description = _hazardous(requires_lease=True).description()
    assert description["actions"]["heat"]["requiresLease"] is True


def test_the_schema_rejects_a_hazardous_action_without_a_lease():
    action = _hazardous(requires_lease=True).description()["actions"]["heat"]
    schema.validate("ActionDescription", action)
    with pytest.raises(BhmsError) as exc:
        schema.validate("ActionDescription", {**action, "requiresLease": False})
    assert exc.value.code == "INVALID_ARGUMENT" and "requiresLease" in (exc.value.field or "")
