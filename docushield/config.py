"""Central, human-readable configuration. Weights/thresholds are deliberately
exposed so officers / judges can see exactly how a score is produced."""
import os

# ---- Risk score: Risk = 100 - (wV*Validation + wT*(100-Tamper) + wF*Face) ----
WEIGHTS = {"validation": 0.30, "tamper": 0.40, "face": 0.30}

# Bands on the final 0-100 risk score
GREEN_MAX = 30
AMBER_MAX = 65          # 66-100 => RED

# Escalation floors: a weighted average can dilute one strong signal, so a
# critical finding can never be hidden behind good scores elsewhere.
ESCALATION_ENABLED = True
FLOOR_ONE_CRITICAL = GREEN_MAX + 1      # >=1 critical flag  -> at least AMBER
FLOOR_TWO_CRITICAL = AMBER_MAX + 1      # >=2 critical / any hard flag -> RED

# ---- Face matching ----
FACE_BACKEND = os.getenv("DOCUSHIELD_FACE_BACKEND", "auto")  # auto | deepface | demo
FACE_MATCH_MIN = 55.0        # live vs document photo
FACE_REGISTRY_MIN = 55.0     # document photo vs registry photo

# ---- Tampering ----
ELA_QUALITY = 90
ELA_Z_FLAG = 3.5             # robust z-score of a field's ELA vs. sibling fields
FONT_HEIGHT_TOL = 0.08       # relative deviation in glyph height
FONT_STROKE_TOL = 0.25       # relative deviation in stroke width
TAMPER_COMPONENT_WEIGHTS = {"ela": 0.85, "metadata": 0.70, "font": 0.85}
EDITOR_SIGNATURES = ("photoshop", "gimp", "canva", "paint", "pixlr",
                     "snapseed", "lightroom", "affinity", "picsart", "photopea")

# ---- Registry (mock government API) ----
# "local" (default) = everything runs in this one process; the mock registry
# is just a SQLite file queried directly, no network call, no second service.
# "http" = talk to a separately-run registry_service (only needed if you
# deliberately want the two-service Docker Compose setup - see README "Advanced").
REGISTRY_MODE = os.getenv("DOCUSHIELD_REGISTRY_MODE", "local")
REGISTRY_URL = os.getenv("DOCUSHIELD_REGISTRY_URL", "http://127.0.0.1:8001")
REGISTRY_API_KEY = os.getenv("DOCUSHIELD_REGISTRY_KEY", "demo-checkpoint-key")
REGISTRY_TIMEOUT = 4.0

# ---- Audit ledger ----
LEDGER_PATH = os.getenv("DOCUSHIELD_LEDGER", "data/audit_ledger.jsonl")
LEDGER_SALT = os.getenv("DOCUSHIELD_LEDGER_SALT", "change-me-in-deployment")
