# Install or rebuild with any local agent

For hosted agents, see the [Muse native route](muse.md) and [Instinct research/proposal](instinct-proposal.md). These describe capability discovery and the required adaptation; the runnable backend below remains macOS-only. No hosted credentials have been migrated and no hosted connector is claimed to be tested.

## Requirements and boundaries

The portable bundle contains `nara-baby/` and `keychain-credentials/`. Keep them together under any directory. An agent can load `nara-baby/SKILL.md` as instructions even if it does not implement a skills standard. All integration commands are Python/JSON; there is no dependency on Hermes, Codex, Claw, Muse, Instinct, or an MCP server. Compatibility has been checked at the script level, not inside every named agent product.

This version requires macOS, Python 3.10+, an accessible user Keychain, and network access to install Python dependencies and reach Nara's Firebase service. Do not claim Windows/Linux or unattended locked-Keychain operation works. Other platforms require a separately implemented secure backend. Do not add a plaintext fallback.

## Rebuild

From `nara-baby/`:

```sh
python3 scripts/rebuild.py
python3 scripts/run.py onboard
```

`rebuild.py` installs the sibling credential package and pinned dependencies in `~/.local/share/skill-keychain/venv`. It retrieves the upstream Python API from a pinned GitHub commit and verifies SHA-256 before storing it at `~/.local/share/nara-baby/upstream/nara.py`. An existing source file with the correct hash is reused. No agent credentials, app credentials, child choices, or timezone preferences are read, transferred, or created by rebuild.

If folders are separated, pass `--credentials-skill /path/to/keychain-credentials`. The script is repeatable and reuses its runtime location. Requests is pinned to `2.34.2`, keyring to `25.7.0`; transitive dependency resolution can vary, so this is a reproducible procedure with verified API source, not a bit-for-bit environment lock.

## First-run conversation

The agent runs `onboard`, translates the JSON state into a concise request, and continues the user's original task once setup is ready. Example:

1. “Nara needs a saved login. Run this setup command in your own terminal; it uses hidden prompts.” Give `python3 scripts/run.py setup` from the skill directory.
2. “Which timezone should I use?” Skip this question when the session already establishes the timezone and save that value.
3. “Which child should I use by default?” Offer the names returned by child profiles. Keep keys internal; if profile names are unavailable, diagnose the lookup instead of delegating key mapping to the user.

The user can configure timezone and child together:

```sh
python3 scripts/run.py configure --timezone America/Los_Angeles --name 'Child name'
```

The timezone above is an example, not a default. Changing only timezone does not require credentials. Child configuration verifies the selected key through a read-only API call. Name selection uses the profile endpoint; duplicate names require clarification rather than picking the first match.

## Transfers and rebuilding by another agent

Copy the two skill folders or unpack the supplied ZIP. Read `SKILL.md`, then run rebuild. Do not copy `.venv`, build directories, caches, machine preferences, Keychain exports, or a password file. A different machine needs its own local Keychain setup and child/timezone selection. On the same macOS user account, agents reuse the same credential entry and preferences.

To reconstruct the integration from source, use `pyproject.toml` for the shared credential package, `scripts/rebuild.py` for dependency and upstream-source setup, `scripts/nara_cli.py` for onboarding/read commands, and `scripts/nara_client.py` for API access. The tests contain fake accounts and credentials only. `references/api.md` documents the upstream schema and remaining write/timer limitations.

## Validation

From the release root, run `python3 scripts/test.py` with Requests and keyring installed. Add `--upstream /path/to/reviewed/nara.py` to include upstream helper compatibility tests; the runner verifies its digest before executing it. No real account mutation or secret reads occur in these tests. For a live check, `run.py onboard` authenticates and discovers child profiles; it does not create or edit baby records.
