"""Plain-language explanation builder for the officer dashboard."""
from __future__ import annotations

BAND_COPY = {
    "GREEN": ("No issues detected", "No action required beyond the officer's own visual check."),
    "AMBER": ("Needs a closer look", "Recommend secondary inspection before clearing the traveller."),
    "RED": ("Do not clear automatically", "Recommend referral to a supervisor / secondary inspection desk."),
}


def summary_lines(res) -> list[str]:
    lines = []
    title, action = BAND_COPY[res.risk.band]
    lines.append(f"{title}. {action}")
    if res.risk.escalated_by:
        lines.append("Score was escalated above the weighted average because of: " + "; ".join(res.risk.escalated_by) + ".")
    for f in res.all_flags:
        lines.append(f"- {f['title']}: {f['detail']}")
    if not res.all_flags:
        lines.append("- All checks (MRZ, dates, registry, tampering, face match) passed.")
    return lines
