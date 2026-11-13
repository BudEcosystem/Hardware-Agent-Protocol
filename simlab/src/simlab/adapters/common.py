"""Shared plumbing for protocol adapters: declare properties and actions from data, map protocol failures honestly.

An adapter is a BHMS ``DeviceServer`` whose device is described by a *profile* (data: registers, nodes, commands,
entities, tools) rather than by hand-written decorators. ``declare_property`` and ``declare_action`` give the SDK's
decorators a handler with a programmatic signature, so the description, validation (bounds, units, enums) and journaling
all come from the SDK exactly as for a native device.

Honesty rules every adapter follows (they are what "evidence" means for a bridge):

* a value read from a protocol is ``reported`` by that instrument unless the profile says the channel is a measurement
  (``measured``), and a bridge never invents a better label than the profile gives;
* an action is verified (``completionEvidence: measured``) only when the profile names a measured read-back; otherwise it
  completes ``reported`` and the effect stays unverified;
* a protocol refusal that proves nothing was executed (an illegal-value exception, an error-queue entry, a refusal return)
  becomes ``DeviceFault`` with proof (effect ``none``, ``mayHaveActed`` false); a failure to connect before sending is the
  same; a timeout or loss of connection after the command left is *unknown* (an unexpected exception: the SDK records
  ``unknown`` and the reconcile hook resolves it by reading the instrument back).

Thread-safety: one event loop.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.device import Device


class Refused(Exception):
    """The instrument explicitly refused the command; nothing was executed."""


class Unreachable(Exception):
    """The instrument could not be reached before the command was sent; nothing was executed."""


def refusal_fault(exc: Refused | Unreachable, protocol: str) -> DeviceFault:
    """The SDK outcome for a refusal or unreachable instrument: failed, effect none, with proof."""
    what = "refused the command" if isinstance(exc, Refused) else "could not be reached"
    return DeviceFault(f"the {protocol} instrument {what}: {exc}",
                       proof=f"{protocol}: {exc} (the command was not executed)", effect="none",
                       hint="fix the cause named in the message, then retry")


def declare_property(device: Device, name: str, getter: Callable[[], Awaitable[Any]], schema: Any, *, evidence: str,
                     description: str, **options: Any) -> None:
    """Declare a property whose value comes from an async zero-argument ``getter`` (raise to report an invalid read)."""
    getter.__name__ = name
    getter.__doc__ = description
    device.property(getter, name=name, schema=schema, evidence=evidence, description=description, **options)


def declare_action(device: Device, name: str, handler: Callable[..., Awaitable[Any]], *, description: str,
                   params: Mapping[str, Any] | None = None, defaults: Mapping[str, Any] | None = None,
                   returns: Any = None, **options: Any) -> None:
    """Declare an action. ``handler(ctx, **arguments)`` is awaited with the admitted arguments; ``params`` maps argument
    name to an SDK annotation (``Range``, ``OneOf``, ``Text``, ``bool``...)."""
    defaults = defaults or {}
    ordered = sorted((params or {}).items(), key=lambda item: item[0] in defaults)  # required first
    parameters = [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    parameters += [inspect.Parameter(arg, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation,
                                     default=defaults.get(arg, inspect.Parameter.empty)) for arg, annotation in ordered]
    handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters, return_annotation=returns if returns is not None else inspect.Signature.empty)
    handler.__name__ = name
    handler.__doc__ = description
    device.action(handler, name=name, description=description, **options)
