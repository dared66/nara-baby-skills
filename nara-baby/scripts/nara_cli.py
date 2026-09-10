#!/usr/bin/env python3
"""Local setup and short-lived Nara reads. Passwords never appear in argv."""
import argparse
import json
import sys
import re
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from nara_keychain import NaraError, setup_credentials, load_credentials, forget_credentials
from skill_credentials import CredentialError
from nara_client import connected_client, quiet
from nara_config import load_config, save_config
from nara_timezone import resolve_timezone


def setup():
    setup_credentials()
    return {"saved": True, "login_verified": False}


def parser():
    result = argparse.ArgumentParser(description="Nara Baby: local Keychain setup and activity reads")
    subs = result.add_subparsers(dest="command", required=True)
    subs.add_parser("setup", help="Privately enter/update the login in your own terminal")
    subs.add_parser("status", help="Check the Nara entry without displaying credentials or logging in")
    subs.add_parser("forget", help="Delete only the Nara skill's saved login")
    subs.add_parser("onboard", help="Check credentials, timezone and child selection; return the next setup step")
    settings = subs.add_parser("configure", help="Save a timezone and/or a verified default child; no passwords")
    settings.add_argument("--timezone")
    settings.add_argument("--family")
    settings.add_argument("--child")
    settings.add_argument("--name", help="Choose the default child by their profile name")
    settings.add_argument("--label")
    for command in ("children", "history"):
        sub = subs.add_parser(command)
        sub.add_argument("--family")
        sub.add_argument("--timezone")
        if command == "history":
            sub.add_argument("--child")
            sub.add_argument("--type", dest="track_type", help="One type or comma-separated types, e.g. FEED,DIAPER,SLEEP")
            sub.add_argument("--since", help="Inclusive ISO timestamp; filters activity start times")
            sub.add_argument("--until", help="Exclusive ISO timestamp; filters activity start times")
            sub.add_argument("--limit", type=int, default=20)
            sub.add_argument("--display", action="store_true", help="Add local timestamps and readable durations")
    bottle = subs.add_parser('log-bottle', help='Log and verify a bottle without writing a custom script')
    bottle.add_argument('--milk', required=True, choices=['breast-milk', 'formula'])
    bottle.add_argument('--amount', required=True)
    bottle.add_argument('--unit', required=True, choices=['fl-oz'])
    bottle.add_argument('--at', required=True, help='Resolved ISO date and time, including date')
    bottle.add_argument('--expect-child', required=True, help='Expected verified profile name')
    bottle.add_argument('--formula-name')
    bottle.add_argument('--family')
    bottle.add_argument('--child')
    bottle.add_argument('--timezone')
    bottle.add_argument('--check-only', action='store_true', help='Read-only: check whether this exact bottle already exists')
    for command_parser in subs.choices.values():
        command_parser.add_argument("--include-internal", action="store_true", help="Developer diagnostics only: include database identifiers")
    return result


def child_choices(api):
    choices = [{"key": key, "name": profile.get("name")} for key, profile in api.get_children().items()]
    if not choices or any(not isinstance(item["name"], str) or not item["name"].strip() for item in choices):
        raise NaraError("Nara child profiles are missing names. Investigate profile discovery; do not ask the user to decode database keys.")
    return choices


def _execute(args):
    if args.command == "setup":
        return setup()
    if args.command == "status":
        with quiet():
            credentials = load_credentials()
            del credentials
        return {"configured": True, "store": "macOS Keychain", "login_verified": False}
    if args.command == "forget":
        with quiet():
            forget_credentials()
        return {"removed": True}
    config = load_config()
    if args.command == "configure":
        if not any((args.name, args.timezone, args.family, args.child, args.label)):
            raise NaraError("Choose a child name or timezone to configure.")
        if args.label and not args.child:
            raise NaraError("A custom label requires an explicitly selected child.")
        if args.name:
            if args.child:
                raise NaraError("Choose a name or a child key, not both.")
            with connected_client(family=args.family, timezone_name=args.timezone or config.get("timezone")) as api:
                matches = [item for item in child_choices(api) if isinstance(item["name"], str) and item["name"].casefold() == args.name.casefold()]
                if len(matches) != 1:
                    raise NaraError("Child name did not identify one profile. Refresh the child list and clarify the selection.")
                args.child, args.label, args.family = matches[0]["key"], matches[0]["name"], api.family_key
        if args.timezone:
            config["timezone"] = resolve_timezone(args.timezone).key
        if args.family and not args.child:
            raise NaraError("Select the child together with its family.")
        if args.child:
            with connected_client(family=args.family, child=args.child, timezone_name=config.get("timezone")) as api:
                config.update(family=api.family_key, child=args.child)
            config.pop("child_label", None)
        if args.label:
            if not args.child:
                raise NaraError("Provide the verified child key when assigning a label.")
            config["child_label"] = args.label
        save_config(config)
        return {"configured": True, "preferences": config}
    if args.command == "onboard":
        try:
            credentials = load_credentials()
            del credentials
        except (NaraError, CredentialError):
            return {"state": "needs_credentials", "action": "Ask the user to run python3 scripts/run.py setup in their own terminal, or unlock/allow the existing Keychain entry. Never ask for passwords in chat."}
        if not config.get("timezone"):
            return {"state": "needs_timezone", "action": "Ask or use a timezone explicitly established by the user; save it with configure --timezone IANA_ZONE."}
        with connected_client(family=config.get("family"), child=config.get("child"), timezone_name=config["timezone"]) as api:
            choices = child_choices(api)
            if config.get("child"):
                name = next((item["name"] for item in choices if item["key"] == config["child"]), None)
                return {"state": "ready", "family": api.family_key, "child": config["child"], "child_label": name, "timezone": config["timezone"]}
            if not choices or any(not isinstance(item["name"], str) or not item["name"].strip() for item in choices):
                raise NaraError("Nara child profiles are missing names. Investigate profile discovery; do not ask the user to decode database keys.")
            return {"state": "needs_child_selection", "family": api.family_key, "children": choices, "names_available": True,
                    "action": "Ask which child NAME to use by default. Keep database keys internal. Save the choice with configure --name NAME."}
    child = getattr(args, "child", None) or config.get("child")
    family = args.family or config.get("family")
    zone = args.timezone or config.get("timezone")
    if args.command in ('history', 'log-bottle') and not child:
        return {"state": "needs_child_selection", "action": "Run onboard and ask which child to use."}
    if not zone:
        return {"state": "needs_timezone", "action": "Ask for a timezone and run configure --timezone IANA_ZONE."}
    if args.command == 'log-bottle':
        from nara_bottle import bottle_fields, log_bottle
        from nara_timezone import epoch_ms
        bottle_fields(args.amount, args.milk == 'breast-milk', args.formula_name)
        if 'T' not in args.at and ' ' not in args.at:
            raise NaraError('Provide both the resolved date and time for the bottle.')
        begin = epoch_ms(args.at, zone)
        with connected_client(family=family, child=child, timezone_name=zone,
                              allow_writes=not args.check_only) as api:
            name = api.get_children()[child].get('name')
            if not isinstance(name, str) or name.casefold() != args.expect_child.casefold():
                raise NaraError('Selected child does not match the requested name. Resolve the correct profile before logging.')
            result = log_bottle(api, child=child, begin=begin, amount=args.amount,
                                breast_milk=args.milk == 'breast-milk',
                                formula_name=args.formula_name, check_only=args.check_only)
            if 'track' in result:
                result['track'] = display_record(result['track'], api.activity_timezone)
            result.update(child_label=name, timezone=api.activity_timezone)
        return result
    if args.command == "history" and not 1 <= args.limit <= 1000:
        raise NaraError("History limit must be between 1 and 1000.")
    since = until = None
    if args.command == "history":
        from nara_timezone import epoch_ms
        for field in ("since", "until"):
            value = getattr(args, field, None)
            if value and "T" not in value and " " not in value:
                raise NaraError("History boundaries require an ISO date and time.")
        since = epoch_ms(args.since, zone) if args.since else None
        until = epoch_ms(args.until, zone) if args.until else None
        if since is not None and until is not None and since >= until:
            raise NaraError("History until must be after since.")
    with connected_client(family=family, child=child if args.command == "history" else None, timezone_name=zone) as api:
        if args.command == "children":
            return {"family": api.family_key, "children": child_choices(api), "names_available": True}
        tracks = api.get_data()
        selected_types = {item.strip().upper() for item in (args.track_type or "").split(",") if item.strip()}
        records = []
        invalid_times = 0
        for key, track in tracks.items():
            if not isinstance(track, dict) or track.get("childKey") != child:
                continue
            if selected_types and track.get("type") not in selected_types:
                continue
            begin = track.get("beginDt")
            if isinstance(begin, bool) or not isinstance(begin, (int, float)) or not math.isfinite(begin):
                invalid_times += 1
                continue
            if since is not None and begin < since or until is not None and begin >= until:
                continue
            records.append(dict(track, key=key))
        records.sort(key=lambda t: t["beginDt"], reverse=True)
        return {"family": api.family_key, "child": child, "child_label": api.get_children()[child].get("name"), "timezone": api.activity_timezone,
                "coverage": {"basis": "activity_start", "since": args.since, "until": args.until,
                             "matched": len(records), "returned": min(len(records), args.limit),
                             "truncated": len(records) > args.limit, "invalid_timestamps": invalid_times,
                             "source_completeness": "not_guaranteed"},
                "tracks": [display_record(record, api.activity_timezone) if getattr(args, "display", False) else record
                           for record in records[:args.limit]]}


def display_record(record, timezone_name):
    """Add deterministic display fields without changing source values or guessing missing data."""
    result = dict(record)
    local_times, durations = {}, {}
    for field in ("beginDt", "endDt"):
        value = record.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            try:
                local_times[field] = datetime.fromtimestamp(value / 1000, ZoneInfo(timezone_name)).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
    for field in ("breastLeftDuration", "breastRightDuration", "pumpLeftDuration", "pumpRightDuration"):
        value = record.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            minutes, seconds = divmod(int(value / 1000), 60)
            durations[field] = f"{minutes} min {seconds} sec"
    result["display"] = {"local_times": local_times, "durations": durations}
    if record.get('feedType') == 'BOTTLE':
        from nara_bottle import decoded_volume
        try:
            result['display']['volume'] = {'amount': format(decoded_volume(record).normalize(), 'f'), 'unit': 'fl oz'}
        except NaraError:
            result['display']['volume'] = {'status': 'unknown'}
    return result


def public_result(value):
    """Remove implementation identifiers at the output boundary, including nested records."""
    if isinstance(value, list):
        return [public_result(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        normalized = key.replace("_", "").lower()
        if normalized in {"family", "child", "childlabel", "key", "id", "uid", "ord", "etag"} or re.search(r"(?:Keyz?|Keys|ID|IDs|Id|Ids)$|_(?:key|keys|id|ids)$", key) or re.fullmatch(r"-[A-Za-z0-9_-]{19}", key):
            continue
        result[key] = public_result(item)
    if value.get("child_label"):
        result["child"] = value["child_label"]
    return result


def execute(args):
    result = _execute(args)
    return result if getattr(args, "include_internal", False) else public_result(result)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (NaraError, CredentialError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "Nara command failed or was cancelled; no diagnostic details were exposed."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
