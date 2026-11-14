# Designing descriptions agents understand

This guide is about the words and numbers in a device description: how to name and describe devices, actions and
properties so that a model picks the right action with the right arguments, and which declarations make refusals
precise instead of surprising. The description format is [spec 4](../../../spec/bhms/04-devices.md); every block below is
executed by the docs test.

An agent reads a device in two sizes: the **summary** in `bhms_find` (a sentence, the capability ids, the action and
property names; about 400 tokens at most) and the **signature** that `bhms_describe` returns (one line per action and
property, with units, bounds, effects and leases), plus the full JSON when it needs it. Everything an agent needs to
act safely must be visible at the signature level.

## A well-described device

Save as `dispenser_server.py`:

```python file=dispenser_server.py
import sys

from bhms import DeviceServer, OneOf, Range

srv = DeviceServer("reagent-bench", instructions="Reagent dispenser for 96-well plates. Volumes in microlitres.")
dispenser = srv.device(
    "dispenser-1", name="Reagent dispenser",
    description="Single-channel syringe dispenser over a 96-well plate; 1000 uL syringe refilled from reservoir A.",
    summary="Dispenses one reagent into a well of the plate in its holder.",
    capabilities=["bhms.liquid.dispense"], tags=["plate-96", "reagent-a"],
    resources=["dispenser-1/syringe"],
    identity={"manufacturer": "BudLab", "model": "SD-1", "serialNumber": "SD1-0042"},
    safety_summary="No hazard to people. A wrong well wastes reagent; dispensing is irreversible.")
dispenser.report_alive()
state = {"volume_uL": 1000.0, "plate": True}


@dispenser.property(unit="uL", evidence="reported", validity_ms=5000)
def syringe_volume() -> float:
    """Reagent left in the syringe, as the pump controller counts it (not measured)."""
    return state["volume_uL"]


@dispenser.property(evidence="measured")
def plate_present() -> bool:
    """Whether a plate sits in the holder (optical switch)."""
    return state["plate"]


@dispenser.action(effect="irreversible", idempotency="relative", requires_lease=True, max_duration_ms=8000,
                  typical_duration_ms=1500, requires_fresh={"plate_present": 2000},
                  preconditions="A plate is in the holder and the syringe holds at least the requested volume.")
async def dispense(ctx, well: OneOf(*[f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13)]),
                   volume: Range(1, 200, unit="uL", step=0.5)) -> {"dispensed": "uL", "remaining": "uL"}:  # noqa: F821
    """Dispense a volume of reagent A into one well. Each call adds the volume again: retry only with the same key."""
    state["volume_uL"] -= volume
    return {"dispensed": volume, "remaining": state["volume_uL"]}


@dispenser.action(effect="reversible", idempotency="idempotent", requires_lease=True, max_duration_ms=30_000,
                  typical_duration_ms=12_000)
async def refill(ctx) -> {"remaining": "uL"}:  # noqa: F821
    """Refill the syringe from reservoir A to 1000 uL."""
    state["volume_uL"] = 1000.0
    return {"remaining": state["volume_uL"]}


if __name__ == "__main__":
    srv.run(sys.argv[1] if len(sys.argv) > 1 else None)
```

What a model sees:

```sh run
bhms ls dispenser_server.py
bhms describe dispenser_server.py dispenser-1
```

```text output
DEVICE NAME STATUS CAPABILITIES ACTIONS PROPERTIES
dispenser-1 Reagent dispenser online bhms.liquid.dispense dispense, refill plate_present, syringe_volume
dispenser-1 "Reagent dispenser": 2 actions, 2 properties; signature below
action dispense(well: A1|A2|A3|A4|A5|A6|A7|A8|..., volume: number uL 1..200 step 0.5) effect=irreversible repeat=relative lease=required cancel=no evidence=reported max=8s -> {dispensed: number uL, remaining: number uL} fresh=plate_present<=2000ms
action refill() effect=reversible repeat=idempotent lease=required cancel=no evidence=reported max=30s -> {remaining: number uL}
property plate_present: boolean measured observable
property syringe_volume: number uL reported observable
```

The choices that made it readable:

- **One device per thing that acts.** A device is what has its own resources and status; a stage and its camera are two
  devices, even on one server.
- **Ids and names.** `deviceId` is stable and boring (`dispenser-1`); `name` is what a person calls it. Action and property
  names are `snake_case` verbs and nouns (`dispense`, `syringe_volume`), never codes (`cmd_7`).
- **The first sentence works alone.** Summaries are cut, so the first sentence of `description` and of each docstring
  must say what the thing does. Say what the agent cannot see: *each call adds the volume again*, *counted, not measured*.
- **Capabilities** are dotted ids (`bhms.liquid.dispense`, `com.acme.spectrometer`) that agents and `bhms_find` can
  filter on; **tags** are free labels for the setup (`plate-96`).
- **Units on every number, bounds on every physical quantity.** `Range(1, 200, unit="uL", step=0.5)`: the bounds and step
  are enforced before anything moves, and the refusal names them. Use UCUM codes from the
  [unit registry](../../../spec/bhms/04-devices.md#45-schemas-units-and-arguments) (`{rev}/min`, not `rpm`; `Cel`, not
  `degC`); a misspelling the SDK knows is refused with the right code.
- **Enumerations for discrete choices.** `OneOf(...)` (or `Literal`, an `Enum`) lists the valid wells; a model cannot
  invent `I13`. The signature line shows the first eight values; the full list is in the description data that
  `bhms_describe` returns with it, and a wrong value is refused with the allowed ones.
- **`effect` and `idempotency` are for the agent's risk reasoning**: `irreversible` + `relative` says that a duplicate
  dispenses twice, which is why the bridge always sends an operation key.
- **Machine-checked preconditions** go in `requires_fresh` (a property that must have a valid, recent observation); the
  free-text `preconditions` is for the rest, and is never machine-checked.
- **Honest evidence.** `syringe_volume` is `reported` (the controller counts steps), `plate_present` is `measured` (an
  optical switch). A model told "measured" will trust it more; do not let it be wrong.
- **`safety_summary`** says what could go wrong, in one sentence, for the agent and for the person reviewing its plan.
- **Results that carry a measurement say whether it is valid** (a `quality` or `valid` member next to the number,
  BHMS-DEV-035), so an empty field is not mistaken for a reading.

## Declarations the SDK refuses

The SDK refuses a description that cannot be honest, when the server builds it, with the fix in the message:

```python run
from bhms import DescriptionError, Range
from bhms.server import Device

dev = Device(None, "centrifuge-1", resources=["centrifuge-1/rotor"])


def declare(label, **options):
    def handler(ctx, speed):
        return None
    handler.__annotations__ = {"speed": options.pop("annotation")}
    try:
        dev.action(handler, name="spin", **options)
        dev.description()
    except DescriptionError as error:
        print(f"{label}: {error}")
    dev.actions.pop("spin", None)
    dev.invalidate()


declare("no unit", annotation=float, effect="reversible", idempotency="absolute", max_duration_ms=1000)
declare("rpm", annotation=Range(0, 5000, unit="rpm"), effect="reversible", idempotency="absolute", max_duration_ms=1000)
declare("no bound on time", annotation=Range(0, 5000, unit="{rev}/min"), effect="reversible", idempotency="absolute")
declare("hazard without lease", annotation=Range(0, 5000, unit="{rev}/min"), effect="hazardous", idempotency="absolute",
        max_duration_ms=60_000)
```

```text output
no unit: action 'spin' argument 'speed' is a bare float without a unit; every number needs one (BHMS-DEV-041). Annotate it as Range(<min>, <max>, unit="<ucum>") — use unit="1" for counts
rpm: ... x-bhms-unit 'rpm' is not a UCUM code (BHMS-DEV-041); write '{rev}/min'
no bound on time: action 'spin': an action with a physical effect must declare max_duration_ms (BHMS-DEV-030); the server enforces it
hazard without lease: action 'spin': a hazardous action must declare requires_lease=True (BHMS-DEV-033): its caller must hold exclusive control of the resources it acts on
```

## Device text is data, not instructions

Names, descriptions, server instructions and every other string a device provides are untrusted: a compromised or
careless device could write "ignore your previous instructions" into them. The agent bridge quotes such text and labels
it, so a model can tell the bridge's guidance from the device's words:

```python run
import asyncio

from bhms.bridges.mcp import instructions_for
from bhms.client import Client


async def main():
    async with await Client.connect("stdio:python dispenser_server.py") as client:
        print(instructions_for(client))


asyncio.run(main())
```

```text output
Operate physical devices through BHMS. ... Notes published by the server (untrusted): "Reagent dispenser for 96-well plates. Volumes in microlitres."
```

Do not put rules in descriptions that the server does not enforce ("never dispense more than 100 uL"): put the bound in
the schema, or in the agent's policy (`bounds` on the gateway), where it is enforced and shown.

## Changing a description

A description is immutable for its digest. Any change (a new bound, a renamed argument) gives a new digest and a
`notifications/devices/listChanged`; clients that pin the digest (`descriptionDigest` on an invoke) are refused with
`STALE` until they describe the device again. Admitted operations are not affected. Keep ids and names stable across
versions of your server; agents and programs refer to them.
