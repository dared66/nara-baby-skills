#!/usr/bin/env python3
"""Rebuild dependencies from the two portable skill folders; no credentials."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

REVISION = "8f0371cd05d112e3217e594473d0e1dd87615b61"
DIGEST = "fc8358a285544de343f008b80e9056cb31c7833cd1d7d5c9a1e3b3d4fca3e8a0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-skill", type=Path, default=Path(__file__).resolve().parents[2] / "keychain-credentials")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This version requires macOS Keychain; it does not fall back to plaintext on other systems.")
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required.")
    if not (args.credentials_skill / "pyproject.toml").is_file():
        parser.error("Place keychain-credentials beside nara-baby or supply --credentials-skill.")
    root = Path.home() / ".local/share"
    destination = root / "nara-baby/upstream/nara.py"
    content = destination.read_bytes() if destination.exists() else b""
    if hashlib.sha256(content).hexdigest() != DIGEST:
        url = f"https://raw.githubusercontent.com/jfchenier/nara-baby-tracker-api/{REVISION}/nara.py"
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != DIGEST:
            raise RuntimeError("Downloaded API source did not match the reviewed digest")
    environment = root / "skill-keychain/venv"
    if not (environment / "bin/python").is_file():
        venv.EnvBuilder(with_pip=True, symlinks=True).create(environment)
    subprocess.run([str(environment / "bin/python"), "-m", "pip", "install", str(args.credentials_skill.resolve()), "requests==2.34.2"], check=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    print("Runtime ready. Run python3 scripts/run.py onboard. No credentials were read or stored.")


if __name__ == "__main__":
    main()
