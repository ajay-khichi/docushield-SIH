"""End-to-end orchestration: image bytes (+ optional live selfie) -> full
screening result. This is what both the dashboard and the API layer call."""
from __future__ import annotations
import io
from dataclasses import dataclass, field
from PIL import Image

from docushield import ocr, tamper, face, validation, risk
from docushield.registry_client import RegistryUnavailable, get_registry

FLAG_TITLES = {
    "mrz_checksum": "MRZ check-digit failure", "mrz_vz_mismatch": "MRZ / printed-zone mismatch",
    "date_logic": "Impossible document dates", "expired": "Document expired",
    "registry_not_found": "Document not found in registry", "registry_mismatch": "Data mismatch vs. registry",
    "registry_status": "Registry status not active", "watchlist": "Watchlist hit",
}


@dataclass
class ScreeningResult:
    ocr: dict
    validation: "validation.ValidationResult"
    tamper: "tamper.TamperResult"
    face_live: "face.FaceResult | None"
    face_registry: "face.FaceResult | None"
    risk: "risk.RiskResult"
    heatmap: Image.Image
    all_flags: list = field(default_factory=list)


def _validation_flags(v: "validation.ValidationResult") -> list[dict]:
    out = []
    for c in v.checks:
        if c.status == "fail" and c.severity in ("critical", "hard"):
            out.append({"id": c.id, "title": FLAG_TITLES.get(c.id, c.name), "severity": c.severity, "detail": c.detail, "layer": "validation"})
    return out


def _tamper_flags(t: "tamper.TamperResult") -> list[dict]:
    sev = "critical" if t.probability >= 60 else "warn"
    return [{"id": f"tamper_{f['field']}_{f['layer']}", "title": f"Possible tampering - {f['field']} ({f['layer']})",
             "severity": sev, "detail": f["reason"], "layer": f["layer"]} for f in t.flagged_fields]


def screen(doc_bytes: bytes, selfie_bytes: bytes | None = None, checkpoint_id: str = "CHECKPOINT-DEMO-01",
          registry=None, use_registry: bool = True) -> ScreeningResult:
    doc_img = Image.open(io.BytesIO(doc_bytes)); doc_img.load()
    ocr_res = ocr.extract(doc_img)
    reg = registry if registry is not None else (get_registry() if use_registry else None)
    val = validation.run(ocr_res, reg)
    tam = tamper.analyse(doc_img, doc_bytes)
    hm = tamper.heatmap(doc_img, tam)

    doc_photo = face.crop_photo(doc_img)
    live_res = None
    if selfie_bytes:
        live_img = Image.open(io.BytesIO(selfie_bytes)); live_img.load()
        live_res = face.compare(doc_photo, live_img)

    reg_res = None
    if reg is not None and val.registry_state == "ok" and val.registry and val.registry.get("found"):
        try:
            docno = ocr_res["mrz"]["doc_number"] if ocr_res["mrz"] and ocr_res["mrz"]["checks"]["document_number"] else ocr_res["fields"]["doc_number"]
            rphoto = reg.photo(docno)
            if rphoto is not None:
                reg_res = face.compare(doc_photo, rphoto)
        except RegistryUnavailable:
            pass

    flags = _validation_flags(val) + _tamper_flags(tam)
    if live_res and live_res.score < face.C.FACE_MATCH_MIN:
        flags.append({"id": "face_mismatch", "title": "Live face does not match document photo", "severity": "critical",
                     "detail": f"Similarity {live_res.score:.1f}/100 (backend: {live_res.backend}), below the {face.C.FACE_MATCH_MIN:.0f} threshold.",
                     "layer": "face"})
    if reg_res and reg_res.score < face.C.FACE_REGISTRY_MIN:
        flags.append({"id": "registry_photo_mismatch", "title": "Document photo does not match registry photo",
                     "severity": "critical",
                     "detail": f"Similarity {reg_res.score:.1f}/100 (backend: {reg_res.backend}) - the printed photo may have been swapped.",
                     "layer": "face"})

    rr = risk.compute(val.pass_rate, tam.probability, live_res.score if live_res else None, flags)
    return ScreeningResult(ocr=ocr_res, validation=val, tamper=tam, face_live=live_res, face_registry=reg_res,
                           risk=rr, heatmap=hm, all_flags=flags)
