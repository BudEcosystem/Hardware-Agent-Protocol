# Sourced by every trial. User-space only; low priority; bounded threads.
export PATH="$HOME/.local/bin:$PATH"
export LAB="$HOME/hms-lab"
export UV_CACHE_DIR="$LAB/cache/uv"
export OMP_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6 MKL_NUM_THREADS=6
renice -n 10 $$ >/dev/null 2>&1 || true
venv() { # venv <name> <pkgs...>
  local name="$1"; shift
  [ -d "$LAB/venvs/$name" ] || uv venv -q --python 3.12 "$LAB/venvs/$name"
  uv pip install -q --python "$LAB/venvs/$name/bin/python" "$@"
}
