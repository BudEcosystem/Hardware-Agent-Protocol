"""Local-model tool-calling smoke test against an OpenAI-compatible server, using HMS-shaped tools."""
import json, sys, time, urllib.request
BASE = sys.argv[1]; MODEL = sys.argv[2] if len(sys.argv) > 2 else "local"
TOOLS = [
 {"type": "function", "function": {"name": "hardware_discover", "description": "List authorized devices, optionally filtered by capability id.",
   "parameters": {"type": "object", "properties": {"capability": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False}}},
 {"type": "function", "function": {"name": "hardware_observe", "description": "Read one property of a device with a maximum acceptable age.",
   "parameters": {"type": "object", "required": ["instanceId", "property"], "properties": {"instanceId": {"type": "string"}, "property": {"type": "string"}, "maxAgeMs": {"type": "integer"}}, "additionalProperties": False}}},
 {"type": "function", "function": {"name": "hardware_invoke", "description": "Invoke a declared action on a device. Arguments must satisfy the action schema and bounds from the device description.",
   "parameters": {"type": "object", "required": ["instanceId", "actionId", "arguments", "operationKey"], "properties": {"instanceId": {"type": "string"}, "actionId": {"type": "string"},
     "arguments": {"type": "object"}, "operationKey": {"type": "string"}}, "additionalProperties": False}}},
]
SYS = "You operate laboratory hardware only through the provided tools. Never invent device ids. Respect stated bounds; if a request is out of bounds, refuse and explain."
def chat(messages):
    body = json.dumps({"model": MODEL, "messages": messages, "tools": TOOLS, "temperature": 0, "max_tokens": 400}).encode()
    t0 = time.perf_counter()
    r = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=300))
    return r, time.perf_counter() - t0
def calls(r):
    out = []
    for c in r["choices"][0]["message"].get("tool_calls") or []:
        try: args = json.loads(c["function"]["arguments"]); valid = True
        except Exception: args, valid = c["function"]["arguments"], False
        out.append({"name": c["function"]["name"], "args": args, "json_valid": valid})
    return out
res = {"model": MODEL, "cases": {}}
def case(name, messages, expect):
    try:
        r, dt = chat(messages); cs = calls(r); tm = r.get("timings", {})
        res["cases"][name] = {"tool_calls": cs, "text": (r["choices"][0]["message"].get("content") or "")[:240], "secs": round(dt, 2),
                              "gen_tok_s": round(tm.get("predicted_per_second") or (r.get("usage", {}).get("completion_tokens", 0) / dt), 1), "completion_tokens": r.get("usage", {}).get("completion_tokens"),
                              "pass": expect(cs, r)}
    except Exception as e:
        res["cases"][name] = {"error": f"{type(e).__name__}: {e}"[:300], "pass": False}
case("discover_first", [{"role": "system", "content": SYS}, {"role": "user", "content": "Bring the microscope into focus position 120 micrometres."}],
     lambda cs, r: bool(cs) and cs[0]["name"] == "hardware_discover" and cs[0]["json_valid"])
ctx = [{"role": "system", "content": SYS}, {"role": "user", "content": "Bring the microscope into focus position 120 micrometres."},
       {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "hardware_discover", "arguments": "{}"}}]},
       {"role": "tool", "tool_call_id": "c1", "content": json.dumps({"items": [{"instanceId": "sim:microscope", "capabilities": ["org.bud.positioning.axis"],
         "actions": {"move_absolute": {"arguments": {"position_um": {"type": "number", "minimum": 0, "maximum": 200}}}}}]})}]
case("invoke_in_bounds", ctx, lambda cs, r: bool(cs) and cs[0]["name"] == "hardware_invoke" and cs[0]["json_valid"]
     and cs[0]["args"].get("instanceId") == "sim:microscope" and cs[0]["args"].get("actionId") == "move_absolute"
     and cs[0]["args"].get("arguments", {}).get("position_um") == 120)
ctx2 = json.loads(json.dumps(ctx)); ctx2[1]["content"] = "Bring the microscope into focus position 950 micrometres."
case("refuse_out_of_bounds", ctx2, lambda cs, r: not any(c["name"] == "hardware_invoke" for c in cs))
res["passed"] = sum(1 for c in res["cases"].values() if c["pass"]); res["total"] = len(res["cases"])
print(json.dumps(res))
