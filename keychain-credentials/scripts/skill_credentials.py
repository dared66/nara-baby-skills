"""Reusable direct Keychain access. No secret-output CLI or env fallback."""
import argparse
import contextlib
import getpass
import json
import logging
import os
import re
import sys
import warnings


class CredentialError(Exception):
    """Fixed, non-sensitive errors suitable for a tool result."""


@contextlib.contextmanager
def private_io():
    previous = logging.root.manager.disable
    with open(os.devnull, "w") as sink:
        logging.disable(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            logging.disable(previous)


def _backend():
    if sys.platform != "darwin":
        raise CredentialError("This credential store requires macOS Keychain.")
    from keyring.backends.macOS import Keyring
    return Keyring()  # No entry-point/config/env selection or fallback stores.


def _identity(service, account):
    if not isinstance(service, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", service):
        raise CredentialError("Service must be a short lowercase identifier.")
    if not isinstance(account, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}", account):
        raise CredentialError("Account must be a short identifier without spaces.")
    return "local.skills." + service, account


def _validate_record(record):
    if not isinstance(record, dict) or not record or any(
        not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", k)
        or not isinstance(v, str) or not v for k, v in record.items()
    ):
        raise CredentialError("Credentials must contain named, nonempty string fields.")


def load_record(service, account="default"):
    identity = _identity(service, account)
    with private_io():
        try:
            raw = _backend().get_password(*identity)
            if raw is None:
                raise CredentialError("No saved credentials for this service/account. Run local setup.")
            record = json.loads(raw)
            _validate_record(record)
            return record
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Keychain lookup failed. Check access or rerun local setup.") from None


def save_record(service, account, record):
    identity = _identity(service, account)
    _validate_record(record)
    with private_io():
        try:
            _backend().set_password(*identity, json.dumps(record, ensure_ascii=False))
        except Exception:
            raise CredentialError("Could not save credentials to macOS Keychain.") from None


def delete_record(service, account="default"):
    identity = _identity(service, account)
    with private_io():
        try:
            store = _backend()
            if store.get_password(*identity) is not None:
                store.delete_password(*identity)
        except Exception:
            raise CredentialError("Could not remove the selected Keychain entry.") from None


def setup_record(service, account="default", fields=("email", "password")):
    _identity(service, account)
    if not fields or len(set(fields)) != len(fields):
        raise CredentialError("Choose distinct credential field names.")
    if any(not isinstance(field, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", field) for field in fields):
        raise CredentialError("--fields accepts field names such as email password, not credential values.")
    if not sys.stdin.isatty():
        raise CredentialError("Run setup yourself in a local terminal; do not send credentials through chat or tool input.")
    record = {}
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        for field in fields:
            for attempt in range(3):
                value = getpass.getpass(f"{field} (hidden; paste/type, then Enter): ")
                if not value:
                    print(f"{field} was empty. Input is invisible while you type or paste.", file=sys.stderr)
                    continue
                confirmation = getpass.getpass(f"Confirm {field} (hidden): ")
                if value != confirmation:
                    print(f"{field} confirmation did not match. Please try again.", file=sys.stderr)
                    continue
                record[field] = value
                break
            else:
                raise CredentialError(f"Could not capture {field} after three attempts; nothing was saved.")
    save_record(service, account, record)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Skill Keychain setup/status/forget. No command displays credential values.")
    parser.add_argument("command", choices=("setup", "status", "forget"))
    parser.add_argument("--service", required=True)
    parser.add_argument("--account", default="default")
    parser.add_argument("--fields", nargs="+", default=["email", "password"], help="Setup field names, never values")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            setup_record(args.service, args.account, args.fields)
            result = {"saved": True, "login_verified": False}
        elif args.command == "status":
            record = load_record(args.service, args.account)
            del record
            result = {"configured": True, "login_verified": False}
        else:
            delete_record(args.service, args.account)
            result = {"removed": True}
        print(json.dumps(result))
        return 0
    except CredentialError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "Credential command failed or was cancelled; no details were exposed."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
