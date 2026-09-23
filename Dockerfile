# DocuShield - one image, one process (the Streamlit dashboard).
# Everything - OCR, validation, tamper detection, face match, and the mock
# registry lookup - runs inside this single container. No second service,
# no docker-compose needed for normal use.
FROM python:3.11-slim

# Tesseract OCR is a system dependency - Module 1 shells out to the
# `tesseract` binary via pytesseract, so it must be on PATH inside the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Registry DB / audit ledger are written here. On most free hosts (Render's
# free tier included) this is NOT persistent storage - it gets rebuilt with a
# fresh random synthetic dataset on every restart, which is fine since none
# of it is real data. Mount a volume onto this path if you want it to persist.
RUN mkdir -p /app/data

EXPOSE 8501

# Render (and most PaaS hosts) inject a $PORT env var the app must bind to;
# default to 8501 for `docker run` / local use where $PORT isn't set.
ENV PORT=8501
CMD python -c "from synth.bootstrap import ensure_dataset; ensure_dataset()" && \
    streamlit run app.py --server.address 0.0.0.0 --server.port ${PORT} --server.headless true
