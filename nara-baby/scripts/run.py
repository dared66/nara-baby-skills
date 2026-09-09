#!/usr/bin/env python3
"""Agent-independent launcher; no dependency install or credential entry implicit."""
import json
import os
from pathlib import Path
import sys

python = Path.home() / ".local/share/skill-keychain/venv/bin/python"
if not python.is_file():
    print(json.dumps({"state": "needs_runtime", "action": "Run python3 scripts/rebuild.py from the nara-baby skill folder."}))
    sys.exit(2)
os.execv(str(python), [str(python), str(Path(__file__).with_name("nara_cli.py")), *(sys.argv[1:] or ["onboard"])])
