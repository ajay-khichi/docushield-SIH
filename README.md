# DocuShield

AI-assisted document screening for border checkpoints — SIH 2026, Problem Statement 26188
(Ministry of Home Affairs / SSB — AI-Based Fake Identity & Document Screening System).

Upload a scanned/photographed identity document plus a live photo of the bearer, get a
**0–100 risk score (GREEN / AMBER / RED)** back in a couple of seconds, with a
field-by-field, plain-language explanation an officer can act on. It's a
**decision-support tool** — the app never auto-clears or auto-denies anyone; every
screening ends in a human officer decision, logged to an audit trail.

100% of the data is synthetic: procedurally generated faces, a fabricated "Republic of
Utopia" mock passport, and a fabricated mock government registry. No real identity or
biometric data anywhere, so it can be run, demoed and put online with zero privacy risk.

## How it works (one process, no moving parts to manage)

Everything below runs **inside a single Python/Streamlit app** — there's no separate
server to start, no service-to-service network calls, nothing else to keep running.

```
 Document image  ──►  OCR  ──►  Validation rules  ──►  Risk Scoring  ──►  you see the result
      +                (reads         (MRZ checksum,        ↑↑↑             on one page:
 Live selfie          each field)   dates, "registry"*)  combines all      score, heatmap,
                          │                                 4 signals      explanation,
                          └──►  Tamper Detection (ELA + EXIF + font)  ─────►  officer decision
                          └──►  Face Match (live photo vs. document)  ────►  buttons
```

\* "Registry" here is a small SQLite file bundled with the app, standing in for a real
government database — `docushield/registry_client.py` reads it directly (no network
call). Swapping in a real government API later only means changing this one file.

| Step | File | What it does |
|---|---|---|
| OCR | `docushield/ocr.py` | Tesseract reads each field (name, DOB, MRZ, …) separately for accuracy |
| MRZ checksum | `docushield/mrz.py` | Verifies the passport's machine-readable zone against the ICAO 9303 standard |
| Validation | `docushield/validation.py` | Cross-checks dates, MRZ vs. printed text, and the mock registry |
| Tamper detection | `docushield/tamper.py` | Error Level Analysis + EXIF forensics + font-consistency checks, with a visual heatmap |
| Face match | `docushield/face.py` | Compares the live selfie (and registry photo) to the document photo |
| Risk scoring | `docushield/risk.py` | Combines all four into one transparent 0–100 score |
| Audit trail | `docushield/ledger.py` | Every screening + officer decision, hash-chained so edits are detectable |
| Dashboard | `app.py` | The one Streamlit page that ties all of the above together |
| Synthetic data | `synth/` | Generates the fake faces, fake passport, and the 11 demo scenarios below |

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# System dependency: Tesseract OCR must be installed and on PATH
#   Ubuntu/Debian: sudo apt install tesseract-ocr
#   macOS:         brew install tesseract
#   Windows:       https://github.com/UB-Mannheim/tesseract/wiki

streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`). First launch
auto-generates the mock registry + the 11 demo scenarios below — nothing else to run.

## Run it with Docker

```bash
docker build -t docushield .
docker run -p 8501:8501 docushield
```

Open `http://localhost:8501`.

## Deploy for free (GitHub → Render)

1. Push this folder to a new GitHub repo:
   ```bash
   git init && git add -A && git commit -m "DocuShield"
   git branch -M main
   git remote add origin https://github.com/<your-username>/docushield.git
   git push -u origin main
   ```
2. Go to [render.com](https://render.com) → sign in with GitHub → **New +** → **Web Service**.
3. Pick your `docushield` repo. Render will detect the `Dockerfile` automatically
   (or use **New +** → **Blueprint** instead, which reads `render.yaml` and configures
   everything for you in one click).
4. Environment: **Docker**. Plan: **Free**. Click **Create Web Service**.

That's it — no extra environment variables needed, no second service to deploy. Render
builds the image, starts the container, and gives you a public
`https://docushield-xxxx.onrender.com` URL to share.

**Free-tier notes:** the app sleeps after ~15 minutes of inactivity and takes ~30-60s to
wake up on the next visit (normal for free hosting tiers). Storage isn't persistent, so
the registry reseeds with a fresh random dataset on every restart — harmless, since it's
all synthetic and the 11 named demo scenarios are deterministic either way.

## Demo scenarios

Pick any of these from the sidebar dropdown — no upload needed:

| # | Scenario | Expected result | What it tests |
|---|---|---|---|
| 01 | Genuine document, genuine bearer | GREEN | baseline |
| 02 | Genuine, poor-quality scan | GREEN | robust to blur/noise |
| 03 | DOB altered (sloppy forger) | RED | ELA + EXIF + MRZ mismatch |
| 04 | Expiry extended in print **and** MRZ (careful forger) | RED | MRZ checksum + registry catch it even when image forensics can't |
| 05 | Surname re-typed, different font size | RED | font-consistency check |
| 06 | Photo swapped | AMBER | document photo vs. registry photo |
| 07 | Genuine document, wrong bearer | AMBER | live face match |
| 08 | Physically perfect but **revoked** document | RED | registry status |
| 09 | Watchlist hit | RED | registry watchlist |
| 10 | Fabricated document, not in registry | AMBER | registry existence check |
| 11 | Expired document | AMBER | date validity |

Upload your own document + selfie instead if you'd rather test something custom.

## Tests

```bash
pytest -q
```

26 tests, ~15-20s: unit tests for the MRZ checksum, OCR, tamper detection, validation
rules, risk scoring and audit ledger, plus an integration test that runs the full
pipeline end-to-end over all 11 demo scenarios and checks each lands in the right band.

## Configuration

All thresholds and scoring weights live in `docushield/config.py` — nothing is hidden in
a black box; officers/judges can see exactly how a score is produced.

## Known limitations (called out on purpose, not hidden)

- The face matcher is a lightweight demo (not biometric-grade); `docushield/face.py`
  will automatically use `deepface`/ArcFace instead if you `pip install deepface` — left
  out by default to keep the free-tier deploy small and fast.
- ELA (tamper detection) can miss an edit re-saved at the same JPEG quality as the
  original — this is why validation (MRZ checksum, registry cross-check) is scored
  independently rather than relying on image forensics alone (see scenario 04).
  AI-generated (deepfake) forgeries are a v2 roadmap item.
- Only one document layout ships (`docushield/template.py`); a real layout is one more
  entry in that file.
- `registry_service/` also exposes the same registry lookups as a standalone FastAPI
  service (`uvicorn registry_service.app:app`) if you ever want to split it out into its
  own host — entirely optional, the app above doesn't need it.

## Compliance

No real government ID or biometric data is collected, stored, or transmitted at any
stage — everything is procedurally generated. Production deployment would add end-to-end
encryption, role-based access control, full audit logging and a documented
lawful-purpose basis under India's DPDP Act 2023 / DPDP Rules 2025 before touching any
real citizen data — see `PS26188_Solution_Document.md` for the full compliance framing.
# docushield-SIH
