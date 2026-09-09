"""Nara mapping onto the shared skill-credentials library."""
from skill_credentials import CredentialError, load_record, setup_record, delete_record


class NaraError(Exception):
    pass


def load_credentials():
    try:
        record = load_record("nara-baby")
        return record["email"], record["password"]
    except CredentialError as exc:
        raise NaraError(str(exc)) from None
    except Exception:
        raise NaraError("Nara login is missing required fields. Rerun local setup.") from None


def setup_credentials():
    setup_record("nara-baby", fields=("email", "password"))


def forget_credentials():
    delete_record("nara-baby")
