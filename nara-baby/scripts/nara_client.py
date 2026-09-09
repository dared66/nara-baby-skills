"""Direct Keychain-to-Nara connection for short-lived skill subprocesses."""
import contextlib
import hashlib
import importlib.util
import logging
import os
import time
import uuid
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from nara_keychain import NaraError, load_credentials
from nara_timezone import timezone_client, resolve_timezone

SOURCE = Path.home() / ".local/share/nara-baby/upstream/nara.py"
SOURCE_SHA256 = "fc8358a285544de343f008b80e9056cb31c7833cd1d7d5c9a1e3b3d4fca3e8a0"


def normalize_activity_fields(fields):
    result = dict(fields)
    # Observed app schema differs from the unofficial helper's spelling.
    if result.get("diaperPoopTexture") == "MUSHY":
        result["diaperPoopTexture"] = "MUSH"
    return result


def parse_tracks(payload):
    if not isinstance(payload, dict) or "error" in payload:
        raise NaraError("Nara activity sync failed or returned an unexpected response.")
    result = payload.get("result")
    if not isinstance(result, dict) or "error" in result:
        raise NaraError("Nara activity sync returned an unexpected result.")
    # Live API uses result.trackz; the reviewed wrapper expects result.data.trackz.
    container = result if "trackz" in result else result.get("data")
    if not isinstance(container, dict) or "trackz" not in container:
        raise NaraError("Nara activity response is missing trackz; this does not mean there are no children.")
    tracks = container["trackz"]
    if tracks is None:
        return {}
    if not isinstance(tracks, dict) or any(not isinstance(t, dict) for t in tracks.values()):
        raise NaraError("Nara activity records have an unexpected format.")
    return tracks


@contextlib.contextmanager
def quiet():
    """Discard upstream output; use only inside this single-purpose process."""
    previous = logging.root.manager.disable
    with open(os.devnull, "w") as sink:
        logging.disable(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            logging.disable(previous)


class Transport:
    def __init__(self):
        import requests
        self.session = requests.Session()
        # Don't inherit proxy credentials or .netrc from the parent runtime.
        self.session.trust_env = False

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "identitytoolkit.googleapis.com", "amazing-ripple-221320.firebaseio.com",
            "us-central1-amazing-ripple-221320.cloudfunctions.net",
        } or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise NaraError("Request destination is not an approved Nara endpoint.")
        if kwargs.get("verify") is False:
            raise NaraError("TLS certificate verification cannot be disabled.")
        kwargs["timeout"] = (10, 30)
        kwargs["allow_redirects"] = False
        response = self.session.request(method, url, **kwargs)
        if 300 <= response.status_code < 400:
            raise NaraError("Nara returned an unexpected redirect.")
        return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        self.session.close()


def load_api(transport):
    content = SOURCE.read_bytes()
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise NaraError("Nara API source differs from the reviewed version.")
    spec = importlib.util.spec_from_file_location("_reviewed_nara", SOURCE)
    module = importlib.util.module_from_spec(spec)
    # Execute exactly the bytes whose digest was verified.
    exec(compile(content, str(SOURCE), "exec"), module.__dict__)
    module.requests = transport

    class SelectedAPI(timezone_client(module.NaraAPI)):
        def _do_request(self, method, url, **kwargs):
            readonly = method.upper() == "GET" or (
                method.upper() == "POST" and url == self.CF_URL
                and kwargs.get("json", {}).get("data", {}).get("action") == "/family/trackz/sync2"
            )
            if not readonly and not getattr(self, "_allow_writes", False):
                raise NaraError("Writes require an explicitly enabled client and a selected child.")
            if not readonly and not getattr(self, "_selected_child", None):
                raise NaraError("Select the intended child before writing an activity.")
            response = transport.request(method, url, **kwargs)
            if response.status_code == 401 and readonly:
                self._authenticate()  # No nested history requests; at most one retry.
                parts = urlsplit(url)
                query = [(k, self.id_token if k == "auth" else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
                url = urlunsplit(parts._replace(query=urlencode(query)))
                if "params" in kwargs:
                    kwargs["params"] = dict(kwargs["params"])
                    if "auth" in kwargs["params"]:
                        kwargs["params"]["auth"] = self.id_token
                if "headers" in kwargs:
                    kwargs["headers"] = dict(kwargs["headers"])
                    if "Authorization" in kwargs["headers"]:
                        kwargs["headers"]["Authorization"] = f"Bearer {self.id_token}"
                response = transport.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        def get_children(self):
            response = self._do_request("GET", f"{self.DB_URL}/familyz/{self.family_key}/childz.json?auth={self.id_token}")
            profiles = response.json()
            if profiles is None:
                return {}
            if not isinstance(profiles, dict) or any(not isinstance(p, dict) for p in profiles.values()):
                raise NaraError("Nara child profiles have an unexpected format.")
            return profiles

        def get_data(self):
            response = self._do_request(
                "POST", self.CF_URL,
                json={"data": {"action": "/family/trackz/sync2", "familyKey": self.family_key, "prevSyncKey": None}},
                headers={"Authorization": f"Bearer {self.id_token}"},
            )
            return parse_tracks(response.json())

        def log_activity(self, *args, **kwargs):
            selected = getattr(self, "_selected_child", None)
            if not selected or kwargs.get("childKey", selected) != selected:
                raise NaraError("Select the intended child before logging an activity.")
            return super().log_activity(*args, **normalize_activity_fields(kwargs))

        def log_bottle_feed(self, breast_milk=True, volume_floz=0, formula_name=None, begin_dt=None, **kwargs):
            from nara_bottle import bottle_fields
            fields = bottle_fields(volume_floz, breast_milk, formula_name)
            if set(fields) & set(kwargs):
                raise NaraError('Do not override generated bottle volume fields.')
            return self.log_activity('FEED', begin_dt=begin_dt, **fields, **kwargs)

        def get_track(self, track_id):
            # Mobile-created records may exist only in sync2, not RTDB trackz.
            if not isinstance(track_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", track_id):
                raise NaraError("Invalid activity identifier.")
            track = self.get_data().get(track_id)
            return dict(track, key=track_id) if track is not None else None

        def patch_activity(self, track_id, updates):
            if not getattr(self, "_allow_writes", False):
                raise NaraError("Writes require an explicitly enabled client and a selected child.")
            if not isinstance(updates, dict) or not updates:
                raise NaraError("Provide fields to update.")
            if set(updates) & {"key", "childKey", "familyKey", "etag", "serverUpdateDt", "type", "createUserKey"}:
                raise NaraError("Changing activity identity or server metadata is not supported.")
            updates = normalize_activity_fields(updates)
            selected = getattr(self, "_selected_child", None)
            track = self.get_track(track_id)
            if not selected or not track or track.get("childKey") != selected:
                raise NaraError("Activity is missing from current sync or belongs to another child.")
            if track.get("familyKey", self.family_key) != self.family_key:
                raise NaraError("Activity belongs to another family.")
            payload = dict(track)
            payload.update(updates)
            payload["updateDt"] = int(time.time() * 1000)
            if "beginDt" in updates:
                payload["ord"] = -payload["beginDt"]
            payload["familyKey"] = self.family_key
            # Submit the full current object under its EXISTING ID. Do not create
            # an RTDB shadow record when mobile history is stored elsewhere.
            group = uuid.uuid4().hex
            url = f"{self.DB_URL}/instreamz/familyz/{self.family_key}/trackz/{self.uid}/{group}/value/{track_id}.json?auth={self.id_token}"
            try:
                self._do_request("PUT", url, json=payload)
                for attempt in range(4):
                    fresh = self.get_track(track_id)
                    if fresh and fresh.get("childKey") == selected and all(fresh.get(k) == v for k, v in updates.items()):
                        return track_id
                    if attempt < 3:
                        time.sleep(0.5)
            except Exception:
                raise NaraError("Edit outcome is uncertain. Read the same activity before retrying; do not create a replacement.") from None
            raise NaraError("Edit was submitted but not confirmed by history sync. Read the same activity before retrying.")

        def _authenticate(self):
            response = transport.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.API_KEY}",
                json={"email": self.email, "password": self.password, "returnSecureToken": True},
            )
            response.raise_for_status()
            data = response.json()
            self.id_token, self.uid = data["idToken"], data["localId"]
            if not all(isinstance(v, str) and v for v in (self.id_token, self.uid)):
                raise NaraError("Nara authentication returned an invalid session.")
            self.family_key = getattr(self, "_selected_family", None)
            self.child_key = getattr(self, "_selected_child", None)

    return SelectedAPI


@contextlib.contextmanager
def connected_client(*, family=None, child=None, timezone_name=None, allow_writes=False):
    """Yield a client inside a muted, sanitized, direct-credential boundary.

    Without child/family selection this connection is for discovery only.
    Callers collect their result inside the context and print it after exit.
    """
    api = transport = None
    with quiet():
        try:
            resolve_timezone(timezone_name)
            transport = Transport()
            client_type = load_api(transport)
            email, password = load_credentials()
            try:
                api = client_type(email, password, timezone_name=timezone_name)
            finally:
                email = password = None
            families = transport.get(
                f"{api.DB_URL}/userz/{api.uid}/familyKeyz.json",
                params={"auth": api.id_token},
            )
            families.raise_for_status()
            memberships = families.json() or {}
            if not isinstance(memberships, dict):
                raise NaraError("Nara returned an invalid family list.")
            if family is None:
                if len(memberships) != 1:
                    raise NaraError("Choose a family explicitly for this account.")
                family = next(iter(memberships))
            if family not in memberships:
                raise NaraError("The selected family is not available to this account.")
            api.family_key, api.child_key = family, child
            api._selected_family, api._selected_child = family, child
            api._allow_writes = allow_writes
            if child is not None:
                children = api.get_children()
                if child not in children:
                    raise NaraError("The selected child was not found in this family's profiles.")
            yield api
        except NaraError:
            raise
        except Exception:
            raise NaraError("Nara operation failed. Check Keychain access, login, and connectivity; no raw error was exposed.") from None
        finally:
            if api is not None:
                api.email = api.password = api.id_token = None
            if transport is not None:
                transport.close()
