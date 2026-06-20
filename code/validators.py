from config import CLAIM_STATUS, SEVERITY, ISSUE_TYPES, RISK_FLAGS, OBJECT_PARTS

def _bool(v): return "true" if str(v).lower() in ("true", "1", "yes") else "false"
def _norm(s): return (s or "").strip().lower()
def _pick(val, allowed, default="unknown"):
    v = str(val).strip()
    return v if v in allowed else default

def _risk_flags(val):
    if not val or str(val).strip().lower() == "none": return "none"
    good = [p for p in (x.strip() for x in str(val).split(";")) if p in RISK_FLAGS and p != "none"]
    return "none" if not good else ";".join(dict.fromkeys(good))

def _normalize_image_ids(raw, image_ids):
    allowed = {_norm(i): i for i in image_ids}
    if not raw or _norm(raw) == "none": return "none"
    ids = [allowed[_norm(p.strip())] for p in raw.split(";") if _norm(p.strip()) in allowed]
    return "none" if not ids else ";".join(dict.fromkeys(ids))

def enforce_injection_backstop(out, perception):
    flags = set(out["risk_flags"].split(";")) if out["risk_flags"] != "none" else set()
    if any(img.get("text_instruction_present") for img in (perception.get("per_image") or [])):
        flags.update({"text_instruction_present", "manual_review_required"})
        if out["claim_status"] == "supported":
            out["claim_status"] = "not_enough_information"
            out["supporting_image_ids"] = "none"
            out["claim_status_justification"] = (
                "Instruction-like text detected in image; cannot auto-approve. "
                + out.get("claim_status_justification", "")
            )
    out["risk_flags"] = "none" if not flags else ";".join(sorted(flags))
    return out

def repair_policy_output(out, row, image_ids, perception):
    obj = row["claim_object"]
    fixed = {
        "evidence_standard_met": _bool(out.get("evidence_standard_met", False)),
        "evidence_standard_met_reason": str(out.get("evidence_standard_met_reason", ""))[:500],
        "risk_flags": _risk_flags(out.get("risk_flags", "none")),
        "issue_type": _pick(out.get("issue_type"), ISSUE_TYPES),
        "object_part": _pick(out.get("object_part"), OBJECT_PARTS.get(obj, {"unknown"})),
        "claim_status": _pick(out.get("claim_status"), CLAIM_STATUS, "not_enough_information"),
        "claim_status_justification": str(out.get("claim_status_justification", ""))[:800],
        "supporting_image_ids": _normalize_image_ids(str(out.get("supporting_image_ids", "none")), image_ids),
        "valid_image": _bool(out.get("valid_image", True)),
        "severity": _pick(out.get("severity"), SEVERITY),
    }

    # Hard gate 1: evidence not met → not_enough_information
    if fixed["evidence_standard_met"] == "false":
        fixed["claim_status"] = "not_enough_information"
        fixed["supporting_image_ids"] = "none"

    # Hard gate 2: invalid stock/edited images cannot support approval
    if fixed["valid_image"] == "false" and fixed["claim_status"] == "supported":
        fixed["claim_status"] = "not_enough_information"
        fixed["supporting_image_ids"] = "none"

    # Consistency: not_enough_information never has supporting images
    if fixed["claim_status"] == "not_enough_information":
        fixed["supporting_image_ids"] = "none"

    # Consistency: supported/contradicted must have severity
    if fixed["claim_status"] in ("supported", "contradicted") and fixed["severity"] == "unknown":
        fixed["severity"] = "medium"  # safe default rather than unknown

    return enforce_injection_backstop(fixed, perception)

def fallback_row(row, reason):
    return {
        "user_id": row["user_id"],
        "image_paths": row["image_paths"],
        "user_claim": row["user_claim"],
        "claim_object": row["claim_object"],
        "evidence_standard_met": "false",
        "evidence_standard_met_reason": reason,
        "risk_flags": "none",
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": reason,
        "supporting_image_ids": "none",
        "valid_image": "true",
        "severity": "unknown",
    }