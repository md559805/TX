#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
if [ -f ".venv/bin/activate" ]; then
  . .venv/bin/activate
fi
exec python3 app.py "$@"
