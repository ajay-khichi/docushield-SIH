"""One place that decides whether the synthetic registry / sample pack need to
be (re)built. Called by docker-entrypoint.sh (subprocess) and by app.py
(in-process, for single-service hosting) so both stay in sync."""
from __future__ import annotations
import os


def ensure_dataset(samples_dir: str | None = None, quiet: bool = False) -> None:
    from registry_service import db
    from synth.generate import seed_registry, build_samples, ROOT

    samples_dir = samples_dir or os.path.join(ROOT, "samples")
    if not os.path.exists(db.DB_PATH):
        n = seed_registry()
        if not quiet:
            print(f"[docushield] registry seeded with {n} synthetic records")
    if not os.path.exists(os.path.join(samples_dir, "manifest.json")):
        m = build_samples(samples_dir)
        if not quiet:
            print(f"[docushield] {len(m)} demo scenarios written to {samples_dir}")
