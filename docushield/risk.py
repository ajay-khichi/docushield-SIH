"""Risk Scoring Engine - transparent, configurable, explainable.

  raw   = 100 - (wV*ValidationPassRate + wT*(100-TamperProb) + wF*FaceMatch)
  final = raw, raised to an escalation floor if any critical/hard flag fired.

Why the floor: a weighted average can dilute one decisive signal (e.g. a
revoked passport with a perfect photo would otherwise score 'Green'). The raw
formula score is always shown next to the final one so nothing is hidden."""
from __future__ import annotations
from dataclasses import dataclass, field
from docushield import config as C


@dataclass
class RiskResult:
    raw: float
    final: float
    band: str
    escalated_by: list = field(default_factory=list)
    weights_used: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)


def band_of(score: float) -> str:
    return "GREEN" if score <= C.GREEN_MAX else "AMBER" if score <= C.AMBER_MAX else "RED"


def compute(validation_rate: float, tamper_prob: float, face_score: float | None, flags: list[dict]) -> RiskResult:
    w = dict(C.WEIGHTS)
    parts = {"validation": validation_rate, "tamper": 100.0 - tamper_prob}
    if face_score is not None:
        parts["face"] = face_score
    else:                                   # no live capture: renormalise over what was actually evaluated
        w.pop("face")
    tot = sum(w.values())
    w = {k: v / tot for k, v in w.items()}
    raw = round(100.0 - sum(w[k] * parts[k] for k in w), 1)
    final, why = raw, []
    if C.ESCALATION_ENABLED:
        hard = [f for f in flags if f["severity"] == "hard"]
        crit = [f for f in flags if f["severity"] == "critical"]
        if hard or len(crit) >= 2:
            final = max(final, C.FLOOR_TWO_CRITICAL)
            why = [f["title"] for f in hard + crit]
        elif len(crit) == 1:
            final = max(final, C.FLOOR_ONE_CRITICAL)
            why = [crit[0]["title"]]
    return RiskResult(raw=raw, final=round(final, 1), band=band_of(final), escalated_by=why if final > raw else [],
                      weights_used={k: round(v, 3) for k, v in w.items()},
                      inputs={"validation_pass_rate": validation_rate, "tamper_probability": tamper_prob,
                              "face_match": face_score})
