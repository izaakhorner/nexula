#!/usr/bin/env bash
# Double-click launcher for macOS / Linux.
# Starts the dashboard server and opens it in your browser.
# (On macOS you may need to right-click -> Open the first time, or run:
#   chmod +x start.command   once, so Finder lets you double-click it.)

cd "$(dirname "$0")" || exit 1

# Find a Python 3 interpreter.
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11+ is required but was not found on your PATH."
  echo "Install it from https://www.python.org/downloads/ and try again."
  read -r -p "Press Enter to close."
  exit 1
fi

URL="http://localhost:8791"

# Open the browser shortly after the server comes up (runs in the background).
(
  sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"          # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" # Linux
  fi
) >/dev/null 2>&1 &

echo "Starting the Support Performance Dashboard..."
echo "It will open at $URL"
echo "Leave this window open while you use it. Press Ctrl+C here to stop."
echo

exec "$PY" serve.py
