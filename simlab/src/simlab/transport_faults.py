"""Message-level fault for the client side of a BHMS link: a reply lost after the effect happened (F2).

``LossyClient`` wraps a real ``bhms.client.Client``. ``actions_invoke`` runs the real call to completion first, so the
operation has settled and its effect is in the world, and only then, if the fault plane holds a ``reply_loss`` fault for
the device, throws the reply away and raises ``TimeoutError``, which is what the caller would see when the reply never
arrives. The loss is decided by the fault plane (deterministic, scripted by time or event), never by a wall-clock race.

Thread-safety: one event loop.
"""

from __future__ import annotations

from typing import Any

from bhms.client.client import Client
from simlab.world import World


class LossyClient:
    """A client whose ``actions_invoke`` reply can be lost by a ``reply_loss`` fault; everything else passes through."""

    def __init__(self, client: Client, world: World) -> None:
        self._client, self._world = client, world
        self.replies_lost = 0

    async def actions_invoke(self, device_id: str, action: str, arguments: dict[str, Any], **kw: Any) -> Any:
        result = await self._client.actions_invoke(device_id, action, arguments, **kw)
        if self._world.faults.consume(device_id, "reply_loss"):
            self.replies_lost += 1
            raise TimeoutError(f"the reply to {device_id}.{action} was lost")
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
