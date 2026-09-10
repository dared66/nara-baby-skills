---
name: nara-baby
description: Nara Baby history and logging; use log-bottle and log-diaper for verified entries. Also supports sleep, diapers, pumping, routines and timers.
---

# Nara Baby

Use the unofficial Python wrapper at https://github.com/jfchenier/nara-baby-tracker-api. It connects to the app's Firebase backend; it is not an official Nara API. Source reviewed at commit `8f0371cd05d112e3217e594473d0e1dd87615b61` on 2026-09-08.

For configured history reads and bottle logging, use the self-contained commands below. Read [references/api.md](references/api.md) for other writes, direct Python API use, timers, troubleshooting, or calculations beyond the CLI display fields.

## Quick diaper logging

Use one command from this skill folder for a requested diaper entry:

```sh
python3 scripts/run.py log-diaper --contents both --color yellow --texture mushy --at 2026-01-15T10:30:00-08:00 --expect-child "Baby A"
```

`both` means wet and dirty in the **same** diaper. Other contents: `wet`, `dirty`, `dry`. Include color/texture only when supplied. For "now", use the inbound message timestamp, so retries/readback refer to the same event time. Ambiguous speech (such as conflicting colors) needs one short clarification; never silently drop a color or reinterpret it. Omitted rash/blowout observations are not guessed.

This command selects the configured child, converts ISO time to integer milliseconds, checks for duplicates, submits once, and verifies the requested fields. Do not write custom Python, read source files, reconfigure the child, run onboarding, or fetch history separately for this supported operation. `saved` or `already_recorded` with `verified: true` completes it. On uncertainty use the same parameters with `--check-only`, never another write. The launcher selects the working runtime; plain `python3 -c` is not an alternative.

## Quick bottle logging

For an authorized bottle entry, execute one command from this skill folder (substitute the requested details):

```sh
python3 scripts/run.py log-bottle --milk breast-milk --amount 2.5 --unit fl-oz --at 2026-01-15T10:30:00-08:00 --expect-child "Baby A"
```

Use `--milk formula` for formula, with `--formula-name` only when supplied. This command supports fluid ounces in increments of 0.1, without rounding. Resolve the requested date/time in the configured timezone; ask only for missing consequential details. The child name is checked against the selected live profile. The command validates configuration, checks existing bottles at that time, writes once with a stable ID, and verifies the requested fields and decoded amount through fresh sync. A `saved` or `already_recorded` result with `verified: true` completes the operation. Answer from the receipt's `amount`, `unit`, child and local time.

Do not write a temporary Python script, read implementation files, run a separate onboarding/history check, or separately convert timestamps for this supported command. For a failed or uncertain result, use the same command with **`--check-only`** to inspect without writing; do not rerun a write. A conflicting existing bottle requires inspecting/editing that record rather than creating another. Do not use logging commands for unrequested test entries.

Bottle values are decoded as `Num / 10**Exp`: **2.5 fl oz is Num=25, Exp=1**. The installed adapter repairs the upstream bottle helper's tenfold error. Existing historical records are not automatically rewritten. Combo and pump volume helpers still require the separate schema checks in the reference.

## Quick read on a configured local installation

For "when did the baby last eat?", use `terminal` with its `command` argument to execute this from the installed skill folder:

```sh
python3 scripts/run.py history --type FEED --limit 1 --display
```

In Hermes the registered skill name is `nara-baby` (no plugin prefix). For a combined recent history, use one call with `--type FEED,DIAPER,SLEEP --since 2026-01-15T17:00:00-08:00 --display`. Add `--until` for an exclusive end boundary. Resolve the requested dates once. Filtering uses activity **start** times; for sleep overlapping a boundary, fetch earlier starts and calculate overlap separately. Check `coverage.truncated` and raise `--limit` if necessary (maximum 1000); source completeness is not guaranteed. Do not make separate fetches for each type.

For recent diapers use `--type DIAPER`; for sleep use `--type SLEEP`. Choose a suitable limit for the requested history. The read command itself checks the saved child, family, timezone, runtime and credentials and fetches live records through the read-only client. A successful history read does not require a separate `onboard` call or API-reference read. If it returns a setup state or error, follow the onboarding steps below; never substitute old chat history.

Use the verified `child` name and `timezone` returned in the result. If the child differs from the explicitly requested child, do not answer from those records: discover and select the correct profile for this request. `display.local_times` contains timezone-aware ISO timestamps; `display.durations` contains readable durations for recorded nursing/pumping sides. Missing duration fields are unknown, not zero; running timers are not completed sessions. Source fields remain available unchanged. Report the latest logged activity, not proof of an unlogged event. An empty result means no matching record was returned. No extra timestamp-conversion command is needed.

## First run and returning users

Choose the host route first. In Meta Muse, read [references/muse.md](references/muse.md) and use its native credential/request facilities when available. In hosted Instinct, read [references/instinct-proposal.md](references/instinct-proposal.md) and inspect actual runtime capabilities before implementation. Those hosted routes are documented adaptation workflows, not tested backends. Do not apply the macOS Keychain setup command there or claim hosted support from Python portability alone. Local agents on macOS use the implemented flow below.

This skill is agent-independent. Any agent that can read these instructions and execute local Python can use it; no Hermes, Codex, MCP, or agent-specific API is required. Credential access currently requires macOS. Read [references/portability.md](references/portability.md) for installation, rebuild, and transfer instructions.

For initial setup, missing preferences/credentials, or operations beyond the configured history and bottle commands, run `python3 scripts/run.py onboard` from this skill folder. The script returns JSON describing the next step. Complete onboarding before performing the requested activity operation, then resume that original request.

- `needs_runtime`: run `python3 scripts/rebuild.py` with the host's normal installation permissions. Keep the sibling `keychain-credentials` skill available or specify its path.
- `needs_credentials`: tell the user that Nara needs a login or access to the existing entry. Ask them to run `python3 scripts/run.py setup` locally in their own terminal. That command privately prompts for credentials and stores them in Keychain. Never ask for a password in chat or pass it through tool input. Existing credentials are reused; access errors are not a reason to overwrite them. Resume `onboard` after the user completes setup.
- `needs_timezone`: ask the timezone, or use one already explicitly established in the session. Save it with `python3 scripts/run.py configure --timezone IANA_ZONE`. There is no hardcoded geographic default.
- `needs_child_selection`: show the verified names from the child profiles and ask which child to use by default. Keep database keys internal. Save the choice using `configure --name NAME`. If names are missing, diagnose profile retrieval; do not ask the user to decode keys or export data merely to identify their children.
- `ready`: use the established timezone and default child. An explicitly named different child overrides the default for that request once its key is verified; ask when the intended child is ambiguous. Do not silently change the saved default. For both children, keep their records and summaries separate.

A saved child that can no longer be found or a multi-family error requires renewed selection. A successful login alone is not successful child discovery. Missing or malformed response data is an error, not proof the account has no children.

Credentials are retrieved by the short-lived Python process through the shared `skill-credentials` library, service `local.skills.nara-baby`, account `default`. There is no email/password environment fallback. Never configure Nara secrets through agent-wide environment injection. Non-secret preferences are stored separately in `~/.config/nara-baby/preferences.json`; do not place them in the distributable skill.

Use `scripts/run.py history` for the selected child's history; `--child`/`--family` can explicitly override it. Use `scripts/run.py children` to discover child profiles and names. For API operations beyond these read commands, use `connected_client` as described in the API reference. The wrapper suppresses upstream authentication output and sanitizes failures.

## Read and summarize

Keep database identifiers out of user-facing messages: family/child/activity/user keys, sync cursors, record IDs, and internal preference fields. The CLI omits these by default, including nested history fields. `--include-internal` is only for an operation that needs exact IDs or explicitly requested debugging; do not forward that output into ordinary replies. Keep such IDs inside the script for edits and readback. A ready message should say, for example, “Ready for the selected child in your chosen timezone.” Do not narrate raw JSON fields or announce unsupported capabilities merely because onboarding passed.

Fetch history with `get_data()` and retain the dictionary keys as activity IDs. Fetch one item with `get_track(track_id)`, which resolves the ID through fresh history sync. Mobile-created activities can be absent from the upstream direct RTDB path; that alone does not indicate deletion or staleness. Select the requested child, activity type, and date window before computing totals.

Interpret calendar days in the user's established IANA timezone. Distinguish “today” from “last 24 hours.” Timestamps and raw durations are milliseconds. For sleep spanning the boundary, count the interval overlapping the requested window. Treat open timers separately from completed sessions; missing values are not zero observations. Preserve units and exclude clearly deleted records when the actual response identifies them as such; do not guess an undocumented deletion field.

Give the requested answer with the child, relevant local time/window, and units. State when the returned data's coverage is incomplete or uncertain. Do not claim trends match the app exactly: the upstream trends helper combines children and has volume and open-timer limitations. Calculate from filtered, checked records instead.

## Log, edit, and manage timers

Creation and timer helpers remain experimental. The sync-based edit path has a verified live diaper-edit check plus offline regression tests; onboarding alone does not verify writes. `connected_client` is read-only by default; pass `allow_writes=True` only for a user-authorized write.

Use `connected_client` from [scripts/nara_client.py](scripts/nara_client.py), which includes the executable adapter in [scripts/nara_timezone.py](scripts/nara_timezone.py), not the bare upstream client. It uses the timezone selected during onboarding, including daylight-saving changes. `NARA_TIMEZONE` or an explicit `timezone_name` overrides it for travel or a changed preference. The adapter covers every upstream creation helper, including growth, health, and timer starts. See the reference for construction and timestamp conversion. Existing records retain their original timezone on ordinary edits and timer stops; do not rewrite historical timezone metadata without a request.

A clear request to log, edit, start, pause, resume, or stop an activity authorizes that specific action. Proceed once the child and required details are known; do not add a redundant confirmation. Ask only for consequential missing details, such as milk type, amount/unit, diaper contents, or an ambiguous historical time. Library defaults do not establish what happened.

- Resolve an explicit time with its timezone and date, then convert to epoch milliseconds. Use the current time for “now.” Reject an end before its start. Override the hardcoded `US/Eastern` timezone for every new activity, including helpers without a `tz` argument (see reference).
- Read the relevant recent history before creating an event to avoid duplicating the same requested action. For an edit or timer operation, read the exact activity and verify its family, child, type, and state.
- Prefer `patch_activity` for edits. Passing an existing `track_id` to a logger performs a full replacement and can erase unrelated fields. When changing `beginDt`, also update `ord=-beginDt`; include a fresh `updateDt`.
- Keep the returned activity ID. Edits submit the full current record under its existing ID to the sync queue and verify it through fresh history; they do not create an RTDB shadow record. Creation helpers still write two backend locations and are not atomic. If a request fails after submission, read back the known ID before any retry. Never blindly rerun a create with a new ID. If the result cannot be determined, report the uncertain outcome and stop further writes.
- Read back successful writes and compare the requested fields. Report an event as saved only when verified. Database readback does not establish that every caregiver's mobile app has refreshed.
- Timer operations must use the existing activity ID. Do not start another timer to resume one. Repeatedly resuming the already-running side resets its start and loses elapsed time in this wrapper; treat that request as already satisfied.
- Diaper color/texture fields are `diaperPoopColor` and `diaperPoopTexture`; the observed mushy value is `MUSH`. The adapter corrects the upstream `MUSHY` spelling.
- Use only observed schemas for volume, growth, and medical fields. Log only user-supplied measurements or administered medication details; do not invent doses or infer treatments.

For an unsupported operation, inspect current upstream source or a corresponding user-owned app record. Do not invent a deletion API or payload enum. Streaming is an indefinite listener, suitable only for an explicitly requested monitoring integration with a defined stop/reconnect policy, not a one-time history question.

## Validation

Use mocked HTTP or payload capture for development. The upstream `tests/` examples can authenticate and write real baby records; do not run them as ordinary tests. Skill installation does not authorize live test entries. Live verification requires configured credentials and an actual user-requested operation.
