"""Verification Audit Ledger.

Every screening and every officer decision is appended to a hash-chained,
append-only log: each entry commits to the previous one, so any later edit,
deletion or reordering is detectable. Only pseudonymous data is written - an
HMAC of the document number (not the number), scores, flag IDs, and an
enumerated officer decision. No names, no images, no free text.

`HashChainLedger` is a local stand-in with the same interface a permissioned
blockchain adapter (Hyperledger Fabric chaincode) would implement in phase 2;
its head hash can also be anchored to a Fabric channel periodically."""
from __future__ import annotations
import hashlib, hmac, json, os
from datetime import datetime, timezone
from docushield import config as C

DECISIONS = ("CLEARED", "SECONDARY_INSPECTION", "REFERRED_TO_SUPERVISOR", "DENIED_ENTRY_PENDING_REVIEW")
GENESIS = "0" * 64


def pseudonym(doc_number: str) -> str:
    return hmac.new(C.LEDGER_SALT.encode(), (doc_number or "").upper().encode(), hashlib.sha256).hexdigest()[:24]


def _h(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HashChainLedger:
    def __init__(self, path: str | None = None):
        self.path = path or C.LEDGER_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)

    def entries(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _append(self, payload: dict) -> dict:
        es = self.entries()
        entry = {"index": len(es), "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 **payload, "prev_hash": es[-1]["hash"] if es else GENESIS}
        entry["hash"] = _h(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def record_screening(self, checkpoint_id: str, doc_number: str, risk: dict, flag_ids: list[str]) -> dict:
        return self._append({"type": "SCREENING", "checkpoint": checkpoint_id, "subject": pseudonym(doc_number),
                             "risk_score": risk["final"], "band": risk["band"], "flags": sorted(flag_ids)})

    def record_decision(self, screening_index: int, officer_id: str, decision: str) -> dict:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        return self._append({"type": "DECISION", "ref": screening_index, "officer": officer_id, "decision": decision})

    def verify(self) -> tuple[bool, int | None, str]:
        prev = GENESIS
        for i, e in enumerate(self.entries()):
            if e.get("index") != i:
                return False, i, "entry index out of sequence (entry removed or reordered)"
            if e.get("prev_hash") != prev:
                return False, i, "chain link broken (previous entry changed or removed)"
            if e.get("hash") != _h(e):
                return False, i, "entry content does not match its hash (entry edited)"
            prev = e["hash"]
        return True, None, "ledger intact"


class FabricLedger:   # phase-2 adapter, intentionally not implemented in the prototype
    """Would call Hyperledger Fabric chaincode (RecordScreening / RecordDecision)
    on a permissioned channel run by MHA/SSB/state police nodes."""
    def __init__(self, *a, **k):
        raise NotImplementedError("Fabric adapter is a phase-2 item; use HashChainLedger in the prototype.")
