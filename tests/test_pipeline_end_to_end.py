"""Runs every demo scenario end-to-end (registry omitted - offline check) and
confirms the risk band lands where the scenario expects for signals that do
not require the registry."""
import json, os
import pytest
from docushield.pipeline import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")

# offline (no registry) expectations differ from the full-registry demo for
# scenarios whose only signal is a registry lookup (revoked/watchlist/not-found)
OFFLINE_EXPECT = {
    "01_genuine_clear": ["GREEN"], "02_genuine_lowquality": ["GREEN"],
    "03_dob_edited_ela": ["RED", "AMBER"], "04_expiry_extended_mrz": ["RED", "AMBER"],
    "05_surname_retyped": ["RED", "AMBER"], "07_impersonation": ["AMBER", "RED"],
}


@pytest.mark.skipif(not os.path.exists(os.path.join(SAMPLES, "manifest.json")), reason="sample pack not generated")
@pytest.mark.parametrize("scenario_id", list(OFFLINE_EXPECT))
def test_offline_scenarios(scenario_id):
    manifest = {s["id"]: s for s in json.load(open(os.path.join(SAMPLES, "manifest.json")))}
    s = manifest[scenario_id]
    doc = open(os.path.join(SAMPLES, s["document"]), "rb").read()
    selfie = open(os.path.join(SAMPLES, s["selfie"]), "rb").read()
    res = screen(doc, selfie, registry=None, use_registry=False)
    assert res.risk.band in OFFLINE_EXPECT[scenario_id]
