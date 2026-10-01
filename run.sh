#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8787}"
export PYTHONPATH="$(pwd)/.deps:$(pwd)${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import hikerapi,fastapi,uvicorn' 2>/dev/null; then
  exec .venv/bin/python -m osinsta --web --port "$PORT"
fi

exec python3 -m osinsta --web --port "$PORT"
