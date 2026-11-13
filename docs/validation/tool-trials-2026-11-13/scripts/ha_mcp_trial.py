"""Onboard a throwaway demo Home Assistant, then drive it through the ha-mcp server over MCP stdio."""
import asyncio, json, os, secrets, sys, time, traceback
import httpx
BASE = "http://127.0.0.1:18123"; CID = BASE + "/"
out = {}
tok_file = os.path.expanduser("~/hms-lab/cache/ha_refresh.json")
def token():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        if os.path.exists(tok_file):
            rt = json.load(open(tok_file))["refresh_token"]
            r = c.post("/auth/token", data={"client_id": CID, "grant_type": "refresh_token", "refresh_token": rt}); r.raise_for_status()
            return r.json()["access_token"]
        r = c.post("/api/onboarding/users", json={"client_id": CID, "name": "HMS Lab", "username": "hmslab", "password": secrets.token_urlsafe(18), "language": "en"}); r.raise_for_status()
        r = c.post("/auth/token", data={"client_id": CID, "grant_type": "authorization_code", "code": r.json()["auth_code"]}); r.raise_for_status()
        j = r.json(); json.dump({"refresh_token": j["refresh_token"]}, open(tok_file, "w")); os.chmod(tok_file, 0o600)
        h = {"Authorization": "Bearer " + j["access_token"]}
        for path, body in (("core_config", {}), ("analytics", {}), ("integration", {"client_id": CID, "redirect_uri": CID + "?auth_callback=1"})):
            c.post("/api/onboarding/" + path, json=body, headers=h)
        return j["access_token"]
try:
    tk = token(); h = {"Authorization": "Bearer " + tk}
    with httpx.Client(base_url=BASE, timeout=30, headers=h) as c:
        cfg = c.get("/api/config").json(); states = c.get("/api/states").json()
    dom = {}
    for s in states: dom[s["entity_id"].split(".")[0]] = dom.get(s["entity_id"].split(".")[0], 0) + 1
    out["home_assistant"] = {"version": cfg.get("version"), "entities": len(states), "domains": dict(sorted(dom.items(), key=lambda kv: -kv[1])[:14])}
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        env = {**os.environ, "HOMEASSISTANT_URL": BASE, "HOMEASSISTANT_TOKEN": tk}
        params = StdioServerParameters(command="uvx", args=["--python", "3.14", "ha-mcp@latest"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                def g(o, *names):
                    for n in names:
                        if hasattr(o, n): return getattr(o, n)
                    return None
                init = await s.initialize(); tools = (await s.list_tools()).tools
                info = g(init, "server_info", "serverInfo")
                res = {"server": g(info, "name"), "server_version": g(info, "version"), "tool_count": len(tools),
                       "tool_names": sorted(t.name for t in tools)}
                byname = {t.name: t for t in tools}
                def schema(t): return g(t, "input_schema", "inputSchema") or {}
                res["schemas"] = {n: {"required": schema(byname[n]).get("required"), "properties": sorted(schema(byname[n]).get("properties", {}))}
                                  for n in ("ha_search", "ha_get_state", "ha_call_service", "ha_get_overview", "ha_bulk_control") if n in byname}
                def ann(t):
                    a = g(t, "annotations"); return a.model_dump(exclude_none=True) if a else None
                res["annotations"] = {n: ann(byname[n]) for n in ("ha_get_state", "ha_call_service") if n in byname}
                res["write_tools"] = sum(1 for t in tools if (ann(t) or {}).get("readOnlyHint", (ann(t) or {}).get("read_only_hint")) is False)
                res["destructive_tools"] = sum(1 for t in tools if (ann(t) or {}).get("destructiveHint", (ann(t) or {}).get("destructive_hint")) is True)
                async def call(name, args):
                    if name not in byname: return {"skipped": "no such tool"}
                    try:
                        t0 = time.perf_counter(); r_ = await s.call_tool(name, args)
                        txt = " ".join(getattr(c, "text", "") or "" for c in r_.content)[:700]
                        return {"isError": bool(g(r_, "is_error", "isError")), "ms": round((time.perf_counter() - t0) * 1000), "text": txt}
                    except Exception as e:
                        return {"exception": f"{type(e).__name__}: {e}"[:300]}
                res["calls"] = {
                    "state_before": await call("ha_get_state", {"entity_id": "light.bed_light"}),
                    "turn_on": await call("ha_call_service", {"domain": "light", "service": "turn_on", "entity_id": "light.bed_light"}),
                    "state_after": await call("ha_get_state", {"entity_id": "light.bed_light"}),
                    "retry_turn_on": await call("ha_call_service", {"domain": "light", "service": "turn_on", "entity_id": "light.bed_light"}),
                    "unknown_entity": await call("ha_call_service", {"domain": "light", "service": "turn_on", "entity_id": "light.does_not_exist"}),
                }
                return res
    out["ha_mcp"] = asyncio.run(asyncio.wait_for(run(), 240)); out["ok"] = True
except Exception as e:
    out.update(ok=False, error=f"{type(e).__name__}: {e}"[:500], tb=traceback.format_exc()[-1200:])
print(json.dumps(out))
