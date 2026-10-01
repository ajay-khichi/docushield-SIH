"""The ONLY file in this codebase that talks to an external identity/document
registry. Nothing else - OCR, validation, tamper detection, face match, risk
scoring, the dashboard - ever sees a raw API response or knows where the data
came from. They only call the 3 methods below and read the plain dicts/images
those methods return.

This is on purpose: swapping the synthetic mock registry for a real
government database (DigiLocker or otherwise) later should mean writing ONE
new adapter class in this file and changing ONE config value - not touching
`ocr.py`, `validation.py`, `tamper.py`, `face.py`, `risk.py`, `pipeline.py` or
`app.py` at all. See "Adding a real government API" at the bottom of this
file for the exact steps.

Every adapter must implement this interface:

    health() -> bool
        Is the registry reachable right now?

    verify(payload: dict) -> dict
        payload keys: doc_number, surname, given_names, dob (ISO date str or
        None), date_of_expiry (ISO date str or None), nationality, sex.
        Must return EXACTLY this shape:
          {"found": False}                                   # not found, or:
          {"found": True,
           "status": "ACTIVE" | "REVOKED" | "LOST" | ...,     # any string; only "ACTIVE" is treated as OK
           "field_match": {"surname": bool|None, "given_names": bool|None,
                            "dob": bool|None, "date_of_expiry": bool|None,
                            "nationality": bool|None, "sex": bool|None},
           "watchlist_hit": bool,
           "watchlist_ref": str | None}
        Use None in field_match for anything the caller didn't send / the
        source API can't compare - see validation.py, which skips None.

    photo(doc_number: str) -> PIL.Image.Image | None
        The bearer's photo on file with the registry, or None if unavailable.
        Used only to compare against the document's printed photo (catches a
        swapped photo). Optional to implement well - returning None just
        skips that one check.

Two adapters ship today:
  LocalRegistryClient  - default. Reads the bundled synthetic SQLite DB
                          in-process. No network, no second service.
  RegistryClient        - HTTP adapter for `registry_service/app.py`'s own
                          mock API contract. Only used if you deliberately
                          run that optional standalone service (see README).
"""
from __future__ import annotations
import io
from typing import Protocol
from PIL import Image
from docushield import config as C


class RegistryUnavailable(Exception):
    """An adapter should raise this for network/auth failures it can't
    recover from - the pipeline treats it as 'skip registry checks, warn the
    officer to verify manually' rather than crashing the screening."""


class RegistryProvider(Protocol):
    """Type-checked shape every adapter (including a future real-API one)
    must match. Not enforced at runtime - it's documentation + editor/IDE
    support for whoever writes the next adapter."""
    def health(self) -> bool: ...
    def verify(self, payload: dict) -> dict: ...
    def photo(self, doc_number: str) -> "Image.Image | None": ...


class LocalRegistryClient:
    """Default adapter. Calls the bundled synthetic registry's own lookup
    logic (registry_service/logic.py) directly - in-process, no network."""

    def __init__(self):
        from registry_service import db
        db.init()

    def health(self) -> bool:
        return True

    def verify(self, payload: dict) -> dict:
        from registry_service import logic
        return logic.verify_payload(payload)

    def photo(self, doc_number: str) -> Image.Image | None:
        from registry_service import logic
        from synth.faces import make_face
        row = logic.get_photo_row(doc_number)
        return make_face(row["face_seed"]) if row else None


class RegistryClient:
    """HTTP adapter for the optional standalone `registry_service/app.py`
    mock API (its own request/response contract - see that file). `requests`
    is imported lazily so it isn't a hard dependency of the default
    single-process deployment.

    This class is also the template for a REAL government API adapter later
    - see "Adding a real government API" below."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float | None = None):
        self.base = (base_url or C.REGISTRY_URL).rstrip("/")
        self.headers = {"X-API-Key": api_key or C.REGISTRY_API_KEY}
        self.timeout = timeout or C.REGISTRY_TIMEOUT

    def _call(self, method, path, **kw):
        import requests
        try:
            r = requests.request(method, self.base + path, headers=self.headers, timeout=self.timeout, **kw)
        except requests.RequestException as e:
            raise RegistryUnavailable(str(e)) from e
        if r.status_code == 401:
            raise RegistryUnavailable("registry rejected API key")
        return r

    def health(self) -> bool:
        try:
            return self._call("GET", "/health").ok
        except RegistryUnavailable:
            return False

    def verify(self, payload: dict) -> dict:
        r = self._call("POST", "/v1/verify-document", json=payload)
        r.raise_for_status()
        return r.json()   # already in the internal shape - see module docstring

    def photo(self, doc_number: str) -> Image.Image | None:
        r = self._call("GET", f"/v1/photo/{doc_number}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")


def get_registry() -> RegistryProvider:
    """Single factory the rest of the app calls - the only place that picks
    which adapter is active. Selected by config.REGISTRY_MODE /
    DOCUSHIELD_REGISTRY_MODE env var: 'local' (default) or 'http'.
    Add a new elif branch here for a new real-API adapter (see below)."""
    if C.REGISTRY_MODE == "http":
        return RegistryClient()
    return LocalRegistryClient()


# ---------------------------------------------------------------------------
# Adding a real government API (e.g. DigiLocker) later
# ---------------------------------------------------------------------------
# 1. Write a new class in this file, e.g. DigiLockerClient, implementing the
#    same 3 methods (health / verify / photo) described at the top. The only
#    work is translating DigiLocker's actual field names/response shape into
#    this file's internal dict shape - e.g.:
#
#      class DigiLockerClient:
#          def __init__(self):
#              self.base = C.REGISTRY_URL          # DigiLocker endpoint
#              self.token = C.REGISTRY_API_KEY      # OAuth token / API key
#
#          def health(self) -> bool:
#              ...  # ping DigiLocker's own health/status endpoint
#
#          def verify(self, payload: dict) -> dict:
#              raw = ...  # call DigiLocker's real verify/fetch endpoint
#              return {
#                  "found": raw["exists"],
#                  "status": raw["documentStatus"],
#                  "field_match": {"surname": raw["name"].split()[-1] == payload["surname"], ...},
#                  "watchlist_hit": False,           # DigiLocker has no watchlist concept - omit/False
#                  "watchlist_ref": None,
#              }
#
#          def photo(self, doc_number: str):
#              ...  # only if DigiLocker exposes a photo; else return None
#
# 2. Add one line to get_registry() above: `elif C.REGISTRY_MODE == "digilocker": return DigiLockerClient()`
# 3. Set DOCUSHIELD_REGISTRY_MODE=digilocker (+ DOCUSHIELD_REGISTRY_URL /
#    DOCUSHIELD_REGISTRY_KEY to the real credentials) as env vars.
# That's it - ocr.py, validation.py, tamper.py, face.py, risk.py, pipeline.py
# and app.py need ZERO changes; they only ever call get_registry().verify(...)
# and get_registry().photo(...) and read the normalized dict/image back.
