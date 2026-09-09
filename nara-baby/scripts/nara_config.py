"""Portable local preferences. Never stores login credentials."""
import json
import os
from pathlib import Path
import tempfile


def config_path():
    return Path.home() / ".config/nara-baby/preferences.json"


def load_config():
    path = config_path()
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) - {"timezone", "family", "child", "child_label"}:
        raise ValueError("Invalid Nara preferences")
    if any(not isinstance(v, str) or not v for v in value.values()):
        raise ValueError("Invalid Nara preference value")
    return value


def save_config(value):
    if not isinstance(value, dict) or set(value) - {"timezone", "family", "child", "child_label"} or any(not isinstance(v, str) or not v for v in value.values()):
        raise ValueError("Invalid Nara preferences")
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".preferences-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
