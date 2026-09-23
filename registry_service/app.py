"""MOCK national document registry.

Stands in for the government-operated database. DocuShield gets *API access
only* (never the database), and this API deliberately returns match booleans and
a status - not the stored record - so a checkpoint learns only what it needs.
Run:  uvicorn registry_service.app:app --port 8001"""
import io, os
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from registry_service import db, logic
from synth.faces import make_face

API_KEYS = {os.getenv("REGISTRY_API_KEY", "demo-checkpoint-key"): "CHECKPOINT-DEMO-01"}
app = FastAPI(title="Mock Government Document Registry (synthetic data)", version="0.1")
db.init()
AUDIT: list[dict] = []          # in-memory access log (a real registry keeps its own)


def _auth(key: str | None) -> str:
    if key not in API_KEYS:
        raise HTTPException(401, "invalid or missing API key")
    return API_KEYS[key]


class VerifyRequest(BaseModel):
    doc_number: str
    surname: str | None = None
    given_names: str | None = None
    dob: str | None = None              # ISO date
    date_of_expiry: str | None = None   # ISO date
    nationality: str | None = None
    sex: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "records": db.count(), "synthetic": True}


@app.post("/v1/verify-document")
def verify(req: VerifyRequest, x_api_key: str | None = Header(default=None)):
    who = _auth(x_api_key)
    result = logic.verify_payload(req.model_dump())
    AUDIT.append({"t": datetime.now(timezone.utc).isoformat(), "by": who, "op": "verify", "found": result["found"]})
    return result


@app.get("/v1/photo/{doc_number}")
def photo(doc_number: str, x_api_key: str | None = Header(default=None)):
    who = _auth(x_api_key)
    row = logic.get_photo_row(doc_number)
    AUDIT.append({"t": datetime.now(timezone.utc).isoformat(), "by": who, "op": "photo", "found": bool(row)})
    if not row:
        raise HTTPException(404, "not found")
    buf = io.BytesIO(); make_face(row["face_seed"]).save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/v1/access-log")
def access_log(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return AUDIT[-50:]
