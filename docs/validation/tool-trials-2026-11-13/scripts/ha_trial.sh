#!/usr/bin/env bash
. "$(dirname "$0")/common.sh"; cd "$LAB/trials"
docker volume create hms-lab-ha-config >/dev/null
docker run --rm -v hms-lab-ha-config:/config busybox sh -c 'printf "default_config:\ndemo:\n" > /config/configuration.yaml'
docker ps -a --format '{{.Names}}' | grep -qx hms-lab-ha || docker run -d --name hms-lab-ha --cpus 2 -p 127.0.0.1:18123:8123 -v hms-lab-ha-config:/config ghcr.io/home-assistant/home-assistant:stable >/dev/null
for i in $(seq 120); do curl -fsS -m 2 http://127.0.0.1:18123/api/onboarding >/dev/null 2>&1 && break; sleep 2; done
venv ha httpx mcp 2>>"$LAB/logs/install-ha.log"
"$LAB/venvs/ha/bin/python" ha_mcp_trial.py > "$LAB/results/ha_mcp.json" 2> "$LAB/logs/ha_mcp.log"; echo "ha_mcp exit=$? bytes=$(stat -c %s "$LAB/results/ha_mcp.json")"
