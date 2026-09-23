"""Thin client for the (mock) government registry API. This is the ONLY way
DocuShield touches registry data - swap base URL/key to point at a real API."""
from __future__ import annotations
import io
from PIL import Image
from docushield import config as C


class RegistryUnavailable(Exception):
    pass


class RegistryClient:
    """HTTP transport - talks to registry_service/app.py over the network.
    Only used in the optional advanced two-service setup; `requests` is
    imported lazily here so it isn't a hard dependency of the default
    single-process (local mode) deployment."""

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
        return r.json()

    def photo(self, doc_number: str) -> Image.Image | None:
        r = self._call("GET", f"/v1/photo/{doc_number}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")


class LocalRegistryClient:
    """In-process transport - calls the registry's own lookup logic directly
    (same code the HTTP API runs, see registry_service/logic.py), no network
    hop at all. Used when only a single process can be deployed for free
    (e.g. Streamlit Community Cloud) and running a second service isn't
    practical. Same method signatures as RegistryClient, so the pipeline
    doesn't need to know which transport is in use."""

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


def get_registry():
    """Pick a transport by config.REGISTRY_MODE / DOCUSHIELD_REGISTRY_MODE
    ('local', default - in-process, no second service; or 'http' - talk to a
    separately-run registry_service, only for the optional advanced setup)."""
    return LocalRegistryClient() if C.REGISTRY_MODE == "local" else RegistryClient()
