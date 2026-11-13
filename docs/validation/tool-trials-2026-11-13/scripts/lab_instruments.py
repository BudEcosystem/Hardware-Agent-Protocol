"""Lab instrument twins smoke test: liquid handler, beamline-style scan, SCPI, Modbus, OPC UA."""
import asyncio, json, sys, threading, time, traceback
out = {}
def trial(name):
    def deco(fn):
        try:
            r = fn(); out[name] = {"ok": True, **(r or {})}
        except Exception as e:
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:400], "tb": traceback.format_exc()[-600:]}
        return fn
    return deco

@trial("pylabrobot_liquid_handler")
def _():
    import pylabrobot, pylabrobot.resources as R
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
    def pick(*names):
        for n in names:
            if hasattr(R, n): return getattr(R, n)
        raise AttributeError(f"none of {names}")
    async def run():
        lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=R.STARLetDeck())
        await lh.setup()
        tc = pick("TIP_CAR_480_A00")(name="tips_carrier"); tc[0] = tips = pick("hamilton_96_tiprack_1000uL_filter", "HTF", "HTF_L")(name="tips")
        pc = pick("PLT_CAR_L5AC_A00")(name="plate_carrier"); pc[0] = plate = pick("Cor_96_wellplate_360ul_Fb", "Cos_96_wellplate_360ul_Fb", "Cos_96_DW_1mL")(name="plate")
        lh.deck.assign_child_resource(tc, rails=3); lh.deck.assign_child_resource(pc, rails=15)
        await lh.pick_up_tips(tips["A1:H1"])
        await lh.aspirate(plate["A1:H1"], vols=[50.0] * 8)
        await lh.dispense(plate["A2:H2"], vols=[50.0] * 8)
        await lh.return_tips(); await lh.stop()
        return {"version": getattr(pylabrobot, "__version__", "?"), "wells": plate.num_items, "tips": tips.num_items}
    return asyncio.run(run())

@trial("bluesky_ophyd_scan")
def _():
    import bluesky
    from bluesky import RunEngine
    from bluesky.plans import scan
    from ophyd.sim import det, motor
    docs = []; RE = RunEngine({}); RE(scan([det], motor, -1, 1, 11), lambda n, d: docs.append(n))
    return {"version": bluesky.__version__, "documents": len(docs), "events": docs.count("event")}

@trial("pyvisa_sim_scpi")
def _():
    import pyvisa
    rm = pyvisa.ResourceManager("@sim"); res = rm.list_resources()
    inst = rm.open_resource("ASRL1::INSTR", read_termination="\n", write_termination="\r\n")
    return {"resources": len(res), "idn": inst.query("?IDN").strip()}

@trial("pymodbus_tcp")
def _():
    import pymodbus
    from pymodbus.client import ModbusTcpClient
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
    from pymodbus.server import StartAsyncTcpServer
    try:
        from pymodbus.datastore import ModbusDeviceContext as Ctx; kw = "devices"
    except ImportError:
        from pymodbus.datastore import ModbusSlaveContext as Ctx; kw = "slaves"
    store = Ctx(hr=ModbusSequentialDataBlock(0, list(range(100, 200))))
    context = ModbusServerContext(**{kw: store}, single=True)
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(StartAsyncTcpServer(context=context, address=("127.0.0.1", 15020))), daemon=True).start()
    time.sleep(1.0); c = ModbusTcpClient("127.0.0.1", port=15020); assert c.connect()
    rr = c.read_holding_registers(10, count=4); c.write_register(10, 4242); rr2 = c.read_holding_registers(10, count=1); c.close()
    return {"version": pymodbus.__version__, "read": list(rr.registers), "after_write": list(rr2.registers)}

@trial("asyncua_opcua")
def _():
    import asyncua
    from asyncua import Client, Server, ua, uamethod
    async def run():
        s = Server(); await s.init(); s.set_endpoint("opc.tcp://127.0.0.1:48410/hms/")
        idx = await s.register_namespace("urn:hms:lab"); obj = await s.nodes.objects.add_object(idx, "Stage")
        pos = await obj.add_variable(idx, "Position", 0.0)
        @uamethod
        async def move_to(parent, target):
            await pos.write_value(float(target)); return True
        meth = await obj.add_method(idx, "MoveTo", move_to, [ua.VariantType.Double], [ua.VariantType.Boolean])
        async with s:
            async with Client("opc.tcp://127.0.0.1:48410/hms/") as c:
                o = c.get_node(obj.nodeid); ok = await o.call_method(meth.nodeid, 12.5)
                val = await c.get_node(pos.nodeid).read_value()
        return {"version": asyncua.__version__, "method_ok": bool(ok), "position": val}
    return asyncio.run(run())

print(json.dumps(out))
