"""DocuShield officer dashboard.  Run:  streamlit run app.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
from PIL import Image

# Bridge Streamlit Cloud's secrets manager to plain env vars *before*
# docushield.config (which reads os.getenv at import time) is imported.
import streamlit as st

try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass  # no secrets.toml (e.g. local dev) - fine, env vars / defaults apply

from docushield.pipeline import screen
from docushield.registry_client import get_registry
from docushield import report, config as C
from docushield.ledger import HashChainLedger, DECISIONS
from synth.bootstrap import ensure_dataset

ensure_dataset(quiet=True)  # first run on a fresh host: seed registry + samples once

st.set_page_config(page_title="DocuShield - Officer Console", layout="wide", page_icon="\U0001F6C2")
BAND_COLOR = {"GREEN": "#1a9c4c", "AMBER": "#d99a10", "RED": "#c92a2a"}

if "ledger" not in st.session_state:
    st.session_state.ledger = HashChainLedger()
if "screening_idx" not in st.session_state:
    st.session_state.screening_idx = None
if "result" not in st.session_state:
    st.session_state.result = None

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
manifest = []
if os.path.exists(os.path.join(SAMPLE_DIR, "manifest.json")):
    manifest = json.load(open(os.path.join(SAMPLE_DIR, "manifest.json")))

with st.sidebar:
    st.markdown("## DocuShield")
    st.caption("AI-based fake identity & document screening \u2014 decision support, not an autonomous gatekeeper.")
    checkpoint_id = st.text_input("Checkpoint ID", value="CHECKPOINT-DEMO-01")
    officer_id = st.text_input("Officer ID", value="OFC-1042")
    st.divider()
    st.markdown("### Input")
    src = st.radio("Source", ["Sample scenario", "Upload"], horizontal=True)
    doc_bytes = selfie_bytes = None
    scenario_label = None
    if src == "Sample scenario" and manifest:
        opt = st.selectbox("Scenario", manifest, format_func=lambda s: s["title"])
        doc_bytes = open(os.path.join(SAMPLE_DIR, opt["document"]), "rb").read()
        selfie_bytes = open(os.path.join(SAMPLE_DIR, opt["selfie"]), "rb").read()
        st.caption(opt["story"])
        scenario_label = opt["title"]
    else:
        du = st.file_uploader("Document image", type=["jpg", "jpeg", "png"])
        su = st.file_uploader("Live capture / selfie (optional)", type=["jpg", "jpeg", "png"])
        doc_bytes = du.read() if du else None
        selfie_bytes = su.read() if su else None
    try:
        reg_ok = get_registry().health()
    except Exception:
        reg_ok = False
    st.divider()
    st.markdown("### Registry check")
    _where = "local database (in this app)" if C.REGISTRY_MODE == "local" else C.REGISTRY_URL
    _icon = "\U0001F7E2 available" if reg_ok else "\U0001F534 unavailable"
    st.markdown(f"{_icon} \u2014 `{_where}`")
    run = st.button("Run screening", type="primary", use_container_width=True, disabled=doc_bytes is None)
    st.divider()
    with st.expander("Scoring weights (transparent by design)"):
        st.json(C.WEIGHTS)
        st.caption(f"Green \u2264 {C.GREEN_MAX} \u00b7 Amber \u2264 {C.AMBER_MAX} \u00b7 Red > {C.AMBER_MAX}. "
                  "A single critical finding (e.g. MRZ checksum failure) or any hard finding "
                  "(revoked / watchlist) escalates the band even if the weighted average looks clean.")

st.title("Officer Console")

if run and doc_bytes:
    with st.spinner("Running OCR \u2192 validation \u2192 tamper detection \u2192 face match \u2192 registry ..."):
        t0 = time.time()
        res = screen(doc_bytes, selfie_bytes, checkpoint_id=checkpoint_id, registry=get_registry())
        elapsed = time.time() - t0
    entry = st.session_state.ledger.record_screening(checkpoint_id,
        (res.ocr["mrz"]["doc_number"] if res.ocr["mrz"] else res.ocr["fields"]["doc_number"]) or "UNKNOWN",
        res.risk.__dict__, [f["id"] for f in res.all_flags])
    st.session_state.result = res
    st.session_state.doc_bytes = doc_bytes
    st.session_state.screening_idx = entry["index"]
    st.session_state.elapsed = elapsed
    st.session_state.scenario_label = scenario_label

res = st.session_state.result
if res is None:
    st.info("Pick a scenario or upload a document + live capture in the sidebar, then click **Run screening**.")
    st.stop()

band = res.risk.band
c1, c2, c3 = st.columns([1.1, 1, 1.4])
with c1:
    st.markdown(f"### Risk score")
    st.markdown(f"<div style='font-size:64px;font-weight:800;color:{BAND_COLOR[band]}'>{res.risk.final:.0f}</div>", unsafe_allow_html=True)
    st.markdown(f"<span style='background:{BAND_COLOR[band]};color:white;padding:4px 14px;border-radius:14px;font-weight:600'>{band}</span>", unsafe_allow_html=True)
    st.caption(f"Weighted-average score: {res.risk.raw:.1f}" + (f" \u2192 escalated to {res.risk.final:.0f}" if res.risk.escalated_by else ""))
    st.caption(f"Screened in {st.session_state.get('elapsed', 0):.1f}s \u00b7 ledger entry #{st.session_state.screening_idx}")
with c2:
    st.markdown("### Document image")
    import io as _io
    st.image(Image.open(_io.BytesIO(st.session_state.doc_bytes)), use_container_width=True)
with c3:
    st.markdown("### Tampering heatmap")
    st.image(res.heatmap, use_container_width=True, caption="Brighter = larger compression-error / inconsistency; red boxes = flagged fields")

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Validation pass rate", f"{res.validation.pass_rate:.0f}%")
m2.metric("Tampering probability", f"{res.tamper.probability:.0f}%")
m3.metric("Live face match", f"{res.face_live.score:.0f}%" if res.face_live else "n/a", help=res.face_live.backend if res.face_live else None)
m4.metric("Doc photo vs. registry", f"{res.face_registry.score:.0f}%" if res.face_registry else "n/a")

st.markdown("#### Officer summary")
for line in report.summary_lines(res):
    st.markdown(line)

t_ocr, t_val, t_tmp, t_face, t_reg, t_ledger = st.tabs(
    ["Extracted fields", "Validation", "Tampering detail", "Face verification", "Registry", "Audit ledger"])

with t_ocr:
    fields = res.ocr["fields"]
    st.table({"Field": list(fields.keys()), "Value": [str(v) for v in fields.values()],
             "OCR confidence": [f"{res.ocr['confidence'][k]:.0f}%" for k in fields]})
    if res.ocr["mrz"]:
        st.code(res.ocr["mrz"]["line1"] + "\n" + res.ocr["mrz"]["line2"], language=None)
        st.write({k: ("\u2705" if v else "\u274c") for k, v in res.ocr["mrz"]["checks"].items()})

with t_val:
    for c in res.validation.checks:
        icon = {"pass": "\u2705", "warn": "\u26a0\ufe0f", "fail": "\u274c", "skipped": "\u23ed\ufe0f"}[c.status]
        st.markdown(f"{icon} **{c.name}** \u2014 {c.detail}")

with t_tmp:
    for name, comp in res.tamper.components.items():
        st.markdown(f"**{name.upper()}** \u2014 score {comp['score']:.2f} \u00b7 applicable: {comp['applicable']}")
        st.json(comp["detail"], expanded=False)
    if res.tamper.flagged_fields:
        st.markdown("**Flagged regions**")
        for f in res.tamper.flagged_fields:
            st.markdown(f"- `{f['field']}` ({f['layer']}): {f['reason']}")
    else:
        st.markdown("No fields flagged by ELA / font-consistency checks.")

with t_face:
    if res.face_live:
        st.write(f"Live capture vs. document photo: **{res.face_live.score:.1f}/100** ({res.face_live.backend})")
        if res.face_live.note:
            st.caption(res.face_live.note)
    else:
        st.info("No live capture supplied.")
    if res.face_registry:
        st.write(f"Document photo vs. registry photo: **{res.face_registry.score:.1f}/100** ({res.face_registry.backend})")

with t_reg:
    if res.validation.registry_state == "ok" and res.validation.registry:
        st.json(res.validation.registry)
    elif res.validation.registry_state == "unreachable":
        st.warning("Registry API was unreachable during this screening.")
    else:
        st.info("Registry was not queried.")

with t_ledger:
    entries = st.session_state.ledger.entries()
    ok, bad_i, msg = st.session_state.ledger.verify()
    st.markdown(("\u2705 " if ok else "\u274c ") + f"Chain integrity: {msg}")
    st.dataframe(entries[::-1], use_container_width=True, hide_index=True)

st.divider()
st.markdown("#### Officer decision")
dcols = st.columns(len(DECISIONS))
for col, dec in zip(dcols, DECISIONS):
    if col.button(dec.replace("_", " ").title(), use_container_width=True, key=f"dec_{dec}"):
        st.session_state.ledger.record_decision(st.session_state.screening_idx, officer_id, dec)
        st.success(f"Recorded: {dec} \u2014 written to the audit ledger (entry #{st.session_state.screening_idx}).")
