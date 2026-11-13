#!/usr/bin/env bash
. "$(dirname "$0")/common.sh"; cd "$LAB/trials"
M="$LAB/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
[ -s "$M" ] || curl -fL -C - -m 1800 -o "$M" "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf" 2>"$LAB/logs/llm_download.log"
ls -la "$M" | awk '{print "model_bytes", $5}'
B="$HOME/amd-ai/src/llama.cpp/build/bin"
LD_LIBRARY_PATH="$B" nohup "$B/llama-server" -m "$M" -ngl 99 -c 8192 --jinja -t 6 --host 127.0.0.1 --port 18080 > "$LAB/logs/llama_server.log" 2>&1 &
PID=$!
for i in $(seq 90); do curl -fsS -m 2 http://127.0.0.1:18080/health >/dev/null 2>&1 && break; sleep 2; done
python3 llm_trial.py http://127.0.0.1:18080 > "$LAB/results/llm_tools_gpu.json" 2> "$LAB/logs/llm_trial.log"; echo "llm_tools_gpu exit=$?"
grep -m3 -i -E "offloaded|backend|using device" "$LAB/logs/llama_server.log" | cut -c1-160
kill $PID; wait $PID 2>/dev/null; echo LLM_TRIAL_DONE
