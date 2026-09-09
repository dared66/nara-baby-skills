---
name: keychain-credentials
description: Store and retrieve credentials for local skill scripts through macOS Keychain, with separate service/account entries and hidden local setup. Use when wiring an API integration to credentials without passing secrets through chat, tool output, files, or environment injection.
---

# Shared skill credentials

This implementation is for local macOS scripts. On a hosted agent, prefer its documented native credential/authenticated-request system; a brokered system need not return plaintext through `load_record`. The bundled Nara skill includes a Muse route and an Instinct proposal. Do not infer that this Keychain library implements those platforms or silently fall back to a file. A user-selected plaintext backend is a proposed compatibility option, not an implemented feature here.

Reuse the installed `skill-credentials` Python library, backed by `keyring`'s explicit macOS backend. It has no environment/file fallback and no CLI command that reveals secrets. This is a short-lived library/CLI, not a server or a background service.

Shared runtime: `~/.local/share/skill-keychain/venv/bin/python`.
CLI: `~/.local/share/skill-keychain/venv/bin/skill-credentials`.
Maintained library source: [scripts/skill_credentials.py](scripts/skill_credentials.py).

## Setup

Choose a stable service identifier and account alias; the Keychain service is `local.skills.<service>`. The alias defaults to `default`. Each entry stores a JSON record of named string fields in Keychain's secret value. Email/password is the default schema; API integrations can use `api_key`, `token`, or other named fields.

The user runs this in their own local terminal and types values into hidden prompts:

```sh
~/.local/share/skill-keychain/venv/bin/skill-credentials setup --service nara-baby --fields email password
```

For another service, choose its own identifier and field names. `--account work` can distinguish accounts. Setup replaces only that exact service/account entry. Never send passwords through chat, tool stdin, command arguments, or a terminal automation tool; give the user the local command. Non-TTY setup is refused and an echoing password-input fallback is refused.

`status --service SERVICE --account ACCOUNT` returns configured status only; it does not authenticate with the external service. `forget` removes only the specified entry and requires the user's request to remove it. Do not enumerate unrelated Keychain entries.

## Direct script retrieval

Use the shared Python runtime or install this local package into the integration's dedicated environment. Retrieve inside the process performing the authorized API action:

```python
from skill_credentials import load_record, CredentialError

credentials = load_record("your-service", "default")
# Pass the required field directly to the service's client here.
# Never print credentials, put them into os.environ, or return them to the agent.
```

Catch `CredentialError` at the script boundary; its fixed messages contain no credential values. Sanitize the API client's own errors separately and disable its verbose HTTP output. The shared library suppresses backend Python logging/stdout/stderr; it cannot sanitize downstream clients automatically. No raw-secret `get` CLI or Hermes secret-source environment injection is needed.

Do not run credential operations inside a multithreaded runtime: Python output/log suppression is process-wide. Launch a short-lived, dedicated script instead. Do not spawn subprocesses after retrieval or persist a client containing credentials. Secrets necessarily exist in process memory; clearing references is not guaranteed zeroization. Keychain permissions apply to executables, not individual skills, so this is not isolation against an agent controlling the script.

Nara is the first integration: its `nara_cli.py` uses `load_record("nara-baby")` internally and returns only activity results or fixed errors. It uses the timezone selected during Nara onboarding.

## Maintenance

Build/install using the included `pyproject.toml`. `keyring==25.7.0` is pinned; review upgrades before changing it. Test service/account separation, missing or locked Keychain, hidden setup, and secret-free outputs using a fake backend. Actual Keychain credential changes belong to user setup, not ordinary tests. Official backend documentation: https://keyring.readthedocs.io/en/stable/.
