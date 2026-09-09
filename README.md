# Nara Baby skills

Agent-independent Nara Baby onboarding, history reads, and verified bottle logging, with a reusable macOS Keychain credential adapter. No server or agent-specific API is required. This is an unofficial integration, unaffiliated with Nara.

## What works

- Private local credential setup and direct retrieval by the API process.
- Child discovery from profiles, explicit default selection, and history filtered by child.
- User-selected IANA timezones, daylight-saving validation, and sanitized JSON output.
- Local timestamps, readable durations, and decoded bottle volumes with `history --display`.
- One-command bottle logging with child checks, duplicate detection, corrected volume encoding, and fresh readback.
- Separate service/account entries for other skills using the credential library.

The runnable credential backend requires **macOS and Python 3.10+**. Muse and hosted Instinct documents describe adaptations, not implemented connectors. Bottle logging supports fluid ounces in increments of 0.1 and requires a user-authorized entry. Other write/timer helpers are experimental and require explicit client opt-in; offline payload tests do not establish live write reliability.

## Start

Keep `nara-baby` and `keychain-credentials` beside one another. From `nara-baby`:

```sh
python3 scripts/rebuild.py
python3 scripts/run.py onboard
```

Follow the returned onboarding state. Enter credentials only in your own terminal using `python3 scripts/run.py setup`. Then configure an IANA timezone and select a child by their verified profile name. No family, child, timezone, password, or machine preference is shipped in this bundle. Timezone names in tests are synthetic test cases.

Give any local agent [nara-baby/SKILL.md](nara-baby/SKILL.md). The generic credential library is documented in [keychain-credentials/SKILL.md](keychain-credentials/SKILL.md).

## Test

Install test dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install requests==2.34.2 keyring==25.7.0
.venv/bin/python scripts/test.py
```

Tests use synthetic fixtures, temporary preferences, and a fake credential backend. The runner blocks network connections and real Keychain access. The upstream helper suite is explicitly skipped unless its reviewed source is supplied:

```sh
.venv/bin/python scripts/test.py --upstream /path/to/reviewed/nara.py
```

Rebuild fetches that source separately and verifies its SHA-256. The public bundle does not vendor it. See [THIRD_PARTY.md](THIRD_PARTY.md), [SECURITY.md](SECURITY.md), and [CONTRIBUTING.md](CONTRIBUTING.md).
