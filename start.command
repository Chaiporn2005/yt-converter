#!/bin/bash
# Double-click in Finder (or run in a terminal) to start the converter and open it in the browser.
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
(sleep 1 && open "http://127.0.0.1:${PORT:-8765}") &
exec python3 server.py
