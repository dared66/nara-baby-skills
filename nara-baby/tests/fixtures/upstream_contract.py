"""Original minimal test double for the upstream interface, not vendor code."""


class NaraAPI:
    API_KEY = "public-project-key-fixture"
    DB_URL = "https://amazing-ripple-221320.firebaseio.com"
    CF_URL = "https://us-central1-amazing-ripple-221320.cloudfunctions.net/app"

    def __init__(self, email, password):
        self.email, self.password = email, password
        self.id_token = self.uid = self.family_key = self.child_key = None
        self._authenticate()

    def login(self):
        self._authenticate()

    def get_track(self, track_id):
        return self._do_request("GET", f"{self.DB_URL}/familyz/{self.family_key}/trackz/{track_id}.json?auth={self.id_token}").json()
