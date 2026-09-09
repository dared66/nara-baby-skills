#!/usr/bin/env python3
"""Local setup and short-lived Nara reads. Passwords never appear in argv."""
import argparse
import json
import sys
import re

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
            sub.add_argument("--type", dest="track_type")
            sub.add_argument("--limit", type=int, default=20)
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
    if args.command == "history" and not child:
        return {"state": "needs_child_selection", "action": "Run onboard and ask which child to use."}
    if not zone:
        return {"state": "needs_timezone", "action": "Ask for a timezone and run configure --timezone IANA_ZONE."}
    if args.command == "history" and not 1 <= args.limit <= 1000:
        raise NaraError("History limit must be between 1 and 1000.")
    with connected_client(family=family, child=child if args.command == "history" else None, timezone_name=zone) as api:
        if args.command == "children":
            return {"family": api.family_key, "children": child_choices(api), "names_available": True}
        tracks = api.get_data()
        records = [dict(t, key=k) for k, t in tracks.items() if isinstance(t, dict)
                   and t.get("childKey") == child
                   and (not args.track_type or t.get("type") == args.track_type)]
        records.sort(key=lambda t: t.get("beginDt") or 0, reverse=True)
        return {"family": api.family_key, "child": child, "child_label": api.get_children()[child].get("name"), "timezone": api.activity_timezone,
                "tracks": records[:args.limit]}


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
