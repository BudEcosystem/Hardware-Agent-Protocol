import asyncio, json, threading, time, pymodbus
from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartAsyncTcpServer
ctx = ModbusServerContext(slaves=ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, list(range(100, 200)))), single=True)
loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_until_complete(StartAsyncTcpServer(context=ctx, address=("127.0.0.1", 15020))), daemon=True).start()
time.sleep(1.0); c = ModbusTcpClient("127.0.0.1", port=15020); assert c.connect()
a = c.read_holding_registers(10, count=4).registers; c.write_register(10, 4242); b = c.read_holding_registers(10, count=1).registers; c.close()
print(json.dumps({"ok": True, "version": pymodbus.__version__, "read": list(a), "after_write": list(b)}))
