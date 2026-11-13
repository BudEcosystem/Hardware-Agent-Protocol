from bhms import DeviceServer, Range

srv = DeviceServer("bench-stage")
stage = srv.device("stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])
z = {"um": 0.0}  # a simulated stage: replace with your driver, and use evidence="measured" with a real encoder

@stage.property(unit="um", evidence="simulated")
def position() -> float:
    return z["um"]

@stage.action(effect="reversible", idempotency="absolute", requires_lease=False,
              completion_evidence="reported", max_duration_ms=5000)
async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:  # noqa: F821 - a unit map
    z["um"] = target
    await ctx.progress(0.5)
    return {"position": z["um"]}

if __name__ == "__main__":
    srv.run()        # stdio by default; srv.run("unix:/tmp/stage.sock"), srv.run("ws://127.0.0.1:8765")
