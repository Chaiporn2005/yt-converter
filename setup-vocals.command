#!/bin/bash
# Install the optional local vocal separation engine in its own environment.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PYTHON="${VOCAL_SETUP_PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON="$(command -v "$candidate")"
      break
    fi
  done
fi
if [ -z "$PYTHON" ]; then
  echo "Python 3.12 is needed. Install it with: brew install python@3.12"
  exit 1
fi
rm -f .venv-vocals/.ready
"$PYTHON" -m venv .venv-vocals
.venv-vocals/bin/python -m pip install -r requirements-vocals.txt
.venv-vocals/bin/python -m demucs --help >/dev/null
.venv-vocals/bin/python -c "import soundfile; import torchaudio; assert 'soundfile' in torchaudio.list_audio_backends()"
touch .venv-vocals/.ready
.venv-vocals/bin/python - <<'PYTHON'
import json
import os
from pathlib import Path
settings = Path(os.environ.get("SETTINGS_PATH", Path.home() / "Library" / "Application Support" / "Local Converter" / "settings.json"))
registry = settings.parent / "vocal-engine.json"
registry.parent.mkdir(parents=True, exist_ok=True)
temporary = registry.with_suffix(".tmp")
# Preserve the venv path rather than resolving the Python symlink to Homebrew.
temporary.write_text(json.dumps({"python": str(Path.cwd() / ".venv-vocals" / "bin" / "python")}), encoding="utf-8")
temporary.replace(registry)
PYTHON
echo "Vocal remover ready. Choose Cut vocal in Local Converter."
echo "The AI model downloads automatically the first time you process a song."
