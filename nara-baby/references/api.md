# API setup and implementation notes

Source: [jfchenier/nara-baby-tracker-api](https://github.com/jfchenier/nara-baby-tracker-api), reviewed commit `8f0371cd05d112e3217e594473d0e1dd87615b61`.
Use `nara.py` as the authority for signatures; its README and API reference contain inconsistencies.

## Installed setup and direct Keychain hookup

Normal CLI output omits family, child, activity, user, and sync identifiers, including nested fields. It substitutes the verified child name. Use `--include-internal` only when a script needs IDs for an operation or for explicit diagnostics; never repeat that diagnostic output in ordinary user-facing summaries. This filter is for presentation, not a security boundary. Direct client methods retain full records for editing and verification.

Shared Python runtime: `~/.local/share/skill-keychain/venv/bin/python`.
Reviewed API source: `~/.local/share/nara-baby/upstream/nara.py`; the client verifies its SHA-256 before loading it.
The shared `skill-credentials` package provides macOS Keychain access to multiple skills with separate service/account entries. Nara uses service `local.skills.nara-baby`, account `default`, fields `email` and `password`.

The user runs this once in their own terminal (both values are hidden and confirmed):

```sh
~/.local/share/skill-keychain/venv/bin/skill-credentials setup --service nara-baby --fields email password
```

No password is supplied through chat, a tool, shell arguments, or environment variables. The setup command stores credentials but does not verify the Nara login. The runtime fails if the Keychain entry is missing, invalid, locked, or denied; it never falls back to `.env`.

For agent-independent commands, use `python3 scripts/run.py` from the skill folder. Existing Hermes/Codex installations can also use their installed absolute paths:

```sh
~/.local/share/skill-keychain/venv/bin/python ~/.hermes/skills/nara-baby/scripts/nara_cli.py status
~/.local/share/skill-keychain/venv/bin/python ~/.hermes/skills/nara-baby/scripts/nara_cli.py children
~/.local/share/skill-keychain/venv/bin/python ~/.hermes/skills/nara-baby/scripts/nara_cli.py history --child VERIFIED_CHILD_KEY --limit 20
```

The Codex copy has the same script under `~/.codex/skills/nara-baby/scripts/`. `children` retrieves names and keys from the family child-profile endpoint. `configure --name NAME` selects a verified profile by name. `history` uses the saved child or an explicit child key and supports `--family`, `--type`, `--limit`, and `--timezone`. Multiple families require explicit selection. `setup` and `forget` in the Nara CLI delegate to the shared credential library; run setup locally and forget only on a removal request.

For bottle logging, use the self-contained `log-bottle` command in SKILL.md. For other authorized logging or timer actions, use a short-lived Python script with the skill scripts directory on its import path:

```python
from nara_client import connected_client
from nara_timezone import epoch_ms

with connected_client(family=verified_family, child=verified_child) as api:
    # Perform the user-requested operation with this client here.
    # Collect a result; printing inside the context is intentionally discarded.
    tracks = api.get_data()
# Print only the requested filtered activity result, never the client or secrets.
```

The wrapper loads credentials inside the process, mutes upstream logs/output, applies request timeouts, disallows redirects, disables inherited proxies/.netrc, preserves selection on reauthentication, and clears client credential references on exit. Raw authentication/HTTP exceptions become a fixed error. It does not guarantee memory zeroization or isolation from an agent controlling that process. Use a dedicated process, not a multithreaded Hermes import. The CLI implements reads and verified bottle logging; other API logging helpers require `connected_client(..., allow_writes=True)` and retain the numeric/retry limitations below.

Timezone priority: per-record `tz` (where supported), constructor `timezone_name`, `NARA_TIMEZONE`, then the timezone saved during onboarding (required if no override is provided). Zones are validated with `zoneinfo`. Metadata injection does not shift epoch timestamps. `epoch_ms` interprets naive local datetimes; explicit offsets already specify an instant. Nonexistent spring-forward times are rejected; repeated fall-back times require an explicit offset or `fold=0/1`. Use the same configured zone for calendar-day report boundaries. Existing timer patches preserve the original timezone.

Offline tests (no real credential lookup or API call):

```sh
NARA_SOURCE_FILE=~/.local/share/nara-baby/upstream/nara.py ~/.local/share/skill-keychain/venv/bin/python /absolute/path/to/nara-baby/tests/test_timezone.py
~/.local/share/skill-keychain/venv/bin/python /absolute/path/to/nara-baby/tests/test_keychain_client.py
```

## Endpoints and target selection

Verification on 2026-09-08 found activities at `result.trackz`, not the upstream wrapper's `result.data.trackz`. The installed client accepts both shapes and raises an error for an unknown shape instead of silently reporting no records. The child-profile endpoint supplies verified names; the skill makes no assumption about how many children an account has.

The wrapper defines the Firebase project/API key and these endpoints:

- Identity Toolkit `accounts:signInWithPassword`: email/password to short-lived ID token and UID.
- RTDB `/userz/{uid}/familyKeyz.json`: authenticated user's family keys.
- Cloud Functions action `/family/trackz/sync2`, with selected `familyKey` and `prevSyncKey: null`: returns `result.trackz` as a mapping (legacy nested responses are also accepted).
- RTDB `/familyz/{family_key}/trackz/{track_id}.json`: upstream legacy activity path; not reliable for mobile-created record lookup.
- RTDB `/instreamz/familyz/{family_key}/trackz/{uid}/{sync_group}/value/{track_id}.json`: queue a complete activity for app synchronization.

The installed adapter implements `get_children()` using authenticated GET `/familyz/{family_key}/childz.json`. Each profile's `name` maps directly to its dictionary key, including children with no activity history. This path was identified in [NaraGaiden's exporter](https://github.com/edemaine/NaraGaiden/blob/main/nara_live_export.py) and verified live on 2026-09-08. Select by name in user-facing onboarding, retaining the key internally. The adapter restores family/child selection across reauthentication.

`_do_request()` automatically reauthenticates and retries once on 401 and has no timeout. `_authenticate()` and SSE also call `requests` directly. When adapting for execution, add timeouts to all HTTP paths and preserve family/child selection during login; a typical ordinary request timeout is `(10, 30)` seconds. Bound retries and sanitize errors. Do not assume a timeout means a write failed.

## Method map

Most manual loggers accept `begin_dt` and `**kwargs`, which can include `tz`, `note`, `childKey`, and a preselected unique `track_id`. Supply a fresh ID before submitting a create when implementing recoverable writes, so an uncertain result can be read back.

| Intent | Method and important arguments |
| --- | --- |
| Read history / item | `get_data()` / `get_track(track_id)` |
| Partial edit | `patch_activity(track_id, updates)` |
| Diaper | `log_diaper(pee, poop, dry=False, rash=False, blowout=False, color=None, texture=None, begin_dt=None, **kwargs)` |
| Completed sleep | `log_sleep(begin_dt, end_dt, **kwargs)` |
| Manual nursing | `log_breast_feed(side, duration_minutes, begin_dt=None, **kwargs)` |
| Bottle | `log_bottle_feed(breast_milk, volume_floz, formula_name=None, begin_dt=None, **kwargs)` |
| Solids | `log_solid_feed(begin_dt=None, note=..., **kwargs)` |
| Combo | `log_combo_feed(breast_side, breast_duration_ms, volume_floz, breast_milk, formula_name=None, begin_dt=None, **kwargs)` |
| Completed pump | `log_pump(begin_dt, end_dt, left_vol_floz=None, right_vol_floz=None, **kwargs)` |
| Routine | `log_routine(routine_name, begin_dt=None, **kwargs)` |
| Milestone | `log_milestone(milestone_name, begin_dt=None, **kwargs)` |
| Journal | `log_note(text, begin_dt=None, **kwargs)`; stores `PARENT_NOTE` |
| Growth | `log_growth(weight_lb=None, height_in=None, head_in=None, begin_dt=None)` |
| Health | `log_health(medicine_name=None, temp_f=None, begin_dt=None)` |
| Appointment / vaccine | `log_medical_appointment(doctor_name=None, begin_dt=None, **kwargs)` / `log_vaccine(vaccine_name, begin_dt=None, **kwargs)` |

Live timers: `start_sleep()`, `stop_sleep(track_id)`; `start_breast_feed(side)`, `pause_breast_feed(track_id)`, `resume_breast_feed(track_id, side=None)`, `stop_breast_feed(track_id)`; equivalent pump start/pause/resume methods, and `stop_pump(track_id, left_vol_floz=0, right_vol_floz=0)`.

## Correctness pitfalls

- Upstream `log_activity()` hardcodes `tz="US/Eastern"`. The bundled timezone adapter overrides this before submission for all manual helpers and timer starts, including methods without a timezone parameter. Use it consistently; do not write an incorrect event and then repair it as the normal path.
- The installed bottle adapter now uses Num=amount*10 and Exp=1: 2.5 fl oz is 25/10. This matches the observed app encoding and fixes the tenfold error in the upstream bottle helper. The CLI verifies both total and milk-specific decoded volume. The unmodified upstream bottle helper and combo/pump manual helpers multiply fluid ounces by 100 and store exponent 1, whereas `trends.py` divides by `10 ** exp`. A nominal 4 oz therefore decodes as 40 in the helper. `stop_pump` uses another encoding. Verify a comparable app-created record before using these encodings; do not claim the correct interpretation has been established by the README. Preserve original units and convert mL to US fl oz only when necessary (`1 fl oz = 29.5735295625 mL`).
- Growth numeric encodings also require checking against an app-created measurement. `log_health` switches the type to temperature when temperature is supplied along with medicine; log distinct requested activities separately. No verified medication dose parameter is exposed.
- `log_breast_feed(side="BOTH")` and combo feed split duration equally. Do not silently use this when per-side durations are unknown or unequal.
- Diaper textures accepted by code: `MUCOUS`, `MUSH`, `PEBBLE`, `RUN`, `SOLID`. Upstream's `Seedy` example is invalid. Colors: `BLACK`, `BROWN`, `GRAY`, `GREEN`, `RED`, `YELLOW`.
- Routine names: `BATH`, `NAILTRIM`, `OUTDOOR`, `PLAY`, `READ`, `TUMMYTIME`, `VITAMIN`.
- A dry-only or poop-only diaper must explicitly set `pee=False`; the helper defaults it to true. Do not interpret an unspecified diaper as wet.
- Upstream `_push_payload` performs two writes. The adapter intentionally replaces upstream `patch_activity`: fresh sync supplies the existing record, and edits go through the sync queue without creating a legacy RTDB shadow. See Sync-backed edits below.
- `log_activity(track_id=existing)` replaces the record. Use partial patching for ordinary edits; preserve unknown fields, original creation data, and associations.
- `start_*` helpers generate their own ID internally. To recover reliably from uncertain starts, adapt them to accept a preselected ID, or inspect recent matching records before retrying; do not blindly create another timer.
- Before pause/resume/stop, validate the activity exists and matches the requested timer type. Some stop methods return true without verifying a valid existing timer. Resuming the same running nursing/pump side discards elapsed time. Do not replay an already-applied transition.
- SSE uses `updateDt >= connection time`; it is not a historical sync. Its callback can receive partial patches, ignores deletion payloads, and lacks a durable reconnect loop. Re-fetch an affected record before treating callback data as complete.

## Reporting calculations

Use timezone-aware `datetime` and `zoneinfo.ZoneInfo` for date boundaries. `beginDt`/`endDt` and nursing duration fields are milliseconds. For sleep totals use `max(0, min(end, window_end)-max(begin, window_start))` with completed sessions; describe running sleep separately. Avoid counting overlapping sleep intervals twice. Feed intervals are start-to-start for the same child; wake windows are end-of-sleep to next sleep start. An empty set is not proof no activity happened. Validate each volume's unit/encoding before aggregation and do not combine mL and fl oz as raw numbers.

## Sync-backed edits

Mobile-created activities may appear in `sync2` while `/familyz/.../trackz/ID` returns null. The upstream direct lookup is not a reliable existence check. The adapter's `get_track` now resolves IDs against fresh sync. `patch_activity` requires write opt-in, checks the selected child/family, preserves the full current record, submits it under the existing ID to the documented instream queue, and checks history for the requested values. It never fabricates a persistent RTDB record to compensate for a null lookup.

Missing sync records and identity changes are rejected. Submission is attempted once. An uncertain result requires inspecting the same ID before retrying. This is not a server-side compare-and-swap transaction: concurrent caregiver edits remain a limitation. The app's observed mushy enum is `MUSH`, not the unofficial wrapper's `MUSHY`; the adapter normalizes that spelling. A live diaper edit has been verified via history sync; this does not validate every creation or timer helper.
