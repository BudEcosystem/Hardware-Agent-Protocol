"""Task 7b group B: packaging and developer experience (Task 10 "SDK gaps", Task 11 S8/S9, Task 1 minors)."""

from __future__ import annotations

import pytest

from bhms.client.client import Client
from bhms.server.decorators import DescriptionError
from bhms.server.device import Device
from bhms.server.server import DeviceServer

# ---------------------------------------------------------------------------- B8: who receives the device is explicit


async def _read(tmp_path, declare):
    srv = DeviceServer("getters", state_dir=str(tmp_path))
    dev = srv.device("d-1", name="D")
    dev.report_alive()
    declare(dev)
    await srv.listen(f"unix:{tmp_path}/s.sock")
    client = await Client.connect(f"unix:{tmp_path}/s.sock")
    try:
        return {name: (await client.properties_read("d-1", name, fresh=True)).observation.value for name in dev.properties}
    finally:
        await client.close()
        await srv.close()


async def test_a_getter_default_argument_is_never_replaced_by_the_device(tmp_path):
    """Task 10 gap 4: ``def get(register=register)`` in a loop silently received the device instead of its default."""
    def declare(dev):
        for register in (7, 9):
            @dev.property(name=f"r{register}", unit="1", evidence="reported")
            def get(register=register) -> float:
                return float(register)

    assert await _read(tmp_path, declare) == {"r7": 7.0, "r9": 9.0}


async def test_a_getter_receives_the_device_by_name_or_annotation(tmp_path):
    def declare(dev):
        @dev.property(unit="1", evidence="reported")
        def named(device) -> float:
            return float(len(device.device_id))

        @dev.property(unit="1", evidence="reported")
        def annotated(d: Device, scale=2) -> float:
            return float(len(d.device_id) * scale)

        @dev.property(unit="1", evidence="reported")
        async def keyword_only(*, device, offset=1) -> float:
            return float(len(device.device_id) + offset)

    assert await _read(tmp_path, declare) == {"named": 3.0, "annotated": 6.0, "keyword_only": 4.0}


@pytest.mark.parametrize("source, fragment", [
    ("def bad(x) -> float: return 1.0", "name it 'device'"),                       # an unmarked required parameter
    ("def bad(device, d: Device) -> float: return 1.0", "more than one"),           # two candidates
    ("def bad(*args) -> float: return 1.0", "name it 'device'"),                    # nothing to bind by
    ("def bad(device, other) -> float: return 1.0", "name it 'device'"),            # a second required parameter
])
def test_an_ambiguous_getter_signature_is_refused_when_declared(source, fragment):
    dev = Device(None, "d-1")
    namespace = {"Device": Device}
    exec(source, namespace)  # noqa: S102 - the signatures under test
    with pytest.raises(DescriptionError) as exc:
        dev.property(unit="1", evidence="reported")(namespace["bad"])
    assert fragment in str(exc.value) and "bad" in str(exc.value)
