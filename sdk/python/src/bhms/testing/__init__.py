"""Testing aids shipped with the SDK: the deterministic ``conformance-device`` (``bhms.testing.conformance_device``) and
:func:`connect`, which serves a :class:`~bhms.server.server.DeviceServer` in-process for tests."""

from bhms.testing.harness import connect

__all__ = ["connect"]
