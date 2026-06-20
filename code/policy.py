def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _is_false(val) -> bool:
    if val is False: return True
    return str(val).strip().lower() in ("false", "no", "0")

def _is_true(val) -> bool:
    if val is True: return True
    return str(val).strip().lower() in ("true", "yes", "1")

def _any_image_matches_object(claim_object: str, per_image: list[dict]) -> bool:
    for img in per_image:
        ot = _norm(img.get("object_type", "unknown"))
        if ot == _norm(claim_object):
            return True
    return False

def _parts_match(claimed: str, visible: str) -> bool:
    if not claimed or not visible: return False
    if claimed in ("unknown", "other", ""): return False
    if visible in ("unknown", "other", ""): return False
    return claimed in visible or visible in claimed

def _clean_object_part(part: str, claim_object: str) -> str:
    if not part: return "unknown"
    p = _norm(part)
    obj = _norm(claim_object)
    if p == obj or p in ("car", "laptop", "package", "vehicle", "device", "box", "parcel"):
        return "unknown"
    return part

# ---- ISSUE TYPE NORMALIZATION ----
# Model drifts between near-synonyms (glass_shatter vs crack, broken_part vs dent).
# Canonicalize using a priority-ordered keyword map BEFORE comparing to claim.
ISSUE_SYNONYMS = {
    "glass_shatter": {"shatter", "shattered", "spiderweb", "spider web", "completely cracked", "fully cracked"},
    "crack": {"crack", "cracked", "chip", "chipped", "fracture"},
    "dent": {"dent", "dented", "ding", "dinged", "indent"},
    "scratch": {"scratch", "scratched", "scrape", "scraped", "mark"},
    "broken_part": {"broken", "snapped", "detached", "loose", "not sitting right", "wobbl", "hinge"},
    "water_damage": {"water", "wet", "spill", "liquid", "moisture"},
    "stain": {"stain", "sticky", "residue"},
    "missing_part": {"missing", "not inside", "not in the box", "empty"},
    "torn_packaging": {"torn", "tear", "ripped", "seal broken", "opened"},
    "crushed_packaging": {"crush", "crushed", "squashed", "flattened", "corner damage"},
}

def _canonical_issue(raw_issue: str, severity_wording: str = "") -> str:
    """Map model's free-text issue description to the closest canonical enum value."""
    text = f"{_norm(raw_issue)} {_norm(severity_wording)}"
    for canon, keywords in ISSUE_SYNONYMS.items():
        if any(kw in text for kw in keywords):
            return canon
    if raw_issue and _norm(raw_issue) not in ("unknown", ""):
        return raw_issue
    return "unknown"

def _has_severe_damage_wording(text: str) -> bool:
    severe_words = {"severe", "bad", "totaled", "destroyed", "shattered", "major", "extensive"}
    mild_words = {"minor", "small", "light", "slight", "tiny"}
    t = _norm(text)
    has_severe = any(w in t for w in severe_words)
    has_mild = any(w in t for w in mild_words)
    # If both present, treat as ambiguous (mild wins — conservative)
    if has_mild: return False
    return has_severe


def compute_evidence_standard_met(claim_object, extracted_claim, per_image, cross_image, image_count):
    if not per_image:
        return False, "No usable image observations."

    if not _any_image_matches_object(claim_object, per_image):
        return False, "Submitted images do not clearly show the claimed object type."

    if image_count > 1 and _is_false(cross_image.get("same_object")):
        return False, "Multi-image set does not consistently show the same object."

    claimed_part = _norm(extracted_claim.get("object_part", "unknown"))
    if claimed_part not in ("unknown", "other", ""):
        part_visible = any(
            _parts_match(claimed_part, _norm(img.get("visible_part", "unknown")))
            for img in per_image
        )
        if not part_visible:
            return False, f"Claimed part '{extracted_claim.get('object_part')}' is not clearly visible."

    if _norm(extracted_claim.get("issue_type", "unknown")) == "missing_part":
        if not any(_norm(img.get("visible_part")) in ("contents", "item") for img in per_image):
            return False, "Contents area not visible enough to verify missing-item claim."

    return True, "At least one image shows the claimed object/part clearly enough to evaluate."


def derive_claim_status(extracted_claim, per_image, cross_image, claim_object):
    """
    Deterministic priority order (most certain signal wins first):
    1. Wrong object in image -> contradicted
    2. Claimed part visible AND shows explicitly NO damage -> contradicted
    3. Claimed part visible AND issue matches (canonical) -> supported
    4. Claimed part visible AND general damage_visible=true -> supported
    5. Severe wording claimed but only minor/no damage visible -> contradicted (severity mismatch)
    6. Otherwise -> not_enough_information
    """
    claimed_issue_raw = extracted_claim.get("issue_type", "unknown")
    severity_wording = extracted_claim.get("severity_wording", "")
    claimed_issue = _canonical_issue(claimed_issue_raw, severity_wording)
    claimed_part = _norm(extracted_claim.get("object_part", "unknown"))
    supporting = []

    relevant_images = []
    for img in per_image:
        obj_type = _norm(img.get("object_type", "unknown"))
        if obj_type not in (_norm(claim_object), "unknown", "other", ""):
            return "contradicted", f"Image shows a different object ({obj_type}) than claimed ({claim_object}).", []
        relevant_images.append(img)

    # Filter to images showing the claimed part, if a part was specified
    part_matched_images = relevant_images
    if claimed_part not in ("unknown", "other", ""):
        filtered = [
            img for img in relevant_images
            if _parts_match(claimed_part, _norm(img.get("visible_part", "unknown")))
        ]
        if filtered:
            part_matched_images = filtered

    for img in part_matched_images:
        iid = img.get("image_id", "")
        visible_issue_raw = img.get("visible_issue", "unknown")
        visible_issue = _canonical_issue(visible_issue_raw)
        visible_part = _norm(img.get("visible_part", "unknown"))
        damage_visible = _is_true(img.get("damage_visible", False))

        # No damage visible at the claimed location -> contradicted
        if visible_issue == "none" or (not damage_visible and _norm(visible_issue_raw) == "none"):
            if claimed_issue not in ("none", "unknown", ""):
                if iid: supporting.append(iid)
                return "contradicted", f"Image {iid} shows the claimed part with no visible damage, contradicting the claimed {claimed_issue}.", supporting

        # Canonical issue match -> supported
        if visible_issue == claimed_issue and visible_issue not in ("unknown", "none", ""):
            if iid: supporting.append(iid)
            return "supported", f"Image {iid} shows {visible_issue} on {visible_part or claimed_part}, matching the claim.", supporting

        # General damage visible, issue claimed -> supported (looser match)
        if damage_visible and claimed_issue not in ("none", "unknown", ""):
            if iid: supporting.append(iid)
            return "supported", f"Image {iid} shows visible damage on {visible_part or claimed_part} consistent with the claimed {claimed_issue}.", supporting

    # Severity-mismatch check: user described SEVERE damage, but we found nothing above
    # and at least one relevant image was clearly viewable -> contradicted on severity grounds
    if _has_severe_damage_wording(severity_wording) and part_matched_images:
        any_damage_seen = any(_is_true(img.get("damage_visible", False)) for img in part_matched_images)
        if not any_damage_seen:
            iid = part_matched_images[0].get("image_id", "")
            if iid: supporting.append(iid)
            return "contradicted", f"User described severe damage but image {iid} shows only minor or no visible damage.", supporting

    if _is_false(cross_image.get("same_object")):
        return "not_enough_information", "Images appear to show different objects.", []

    return "not_enough_information", "Observations do not clearly support or contradict the claim.", []


def derive_valid_image(per_image):
    """
    valid_image = false ONLY when:
    - no images at all, OR
    - the image is identified as stock/non-original (per spec: counterfeit evidence invalidates it)
    """
    if not per_image:
        return False
    if any(_is_true(img.get("is_likely_stock_or_edited")) for img in per_image):
        return False
    return True


def derive_severity(extracted_claim, per_image, claim_status):
    if claim_status not in ("supported", "contradicted"):
        return "unknown"
    if claim_status == "contradicted":
        return "none"
    wording = _norm(extracted_claim.get("severity_wording", ""))
    # Strict default to medium; only explicit extremes move off it
    if any(w in wording for w in ("shatter", "totaled", "destroyed", "severe", "extensive")):
        return "high"
    if any(w in wording for w in ("minor", "small", "light", "slight", "tiny")):
        return "low"
    return "medium"


def merge_risk_flags(pregate_injection, history, cross_image, claim_status, per_image):
    flags = set()
    for img in per_image:
        for f in img.get("quality_flags") or []:
            f = _norm(f)
            if f and f != "none": flags.add(f)
        if _is_true(img.get("text_instruction_present")):
            flags.update({"text_instruction_present", "manual_review_required"})
        if _is_true(img.get("is_likely_stock_or_edited")):
            flags.update({"non_original_image", "manual_review_required"})
    if pregate_injection:
        flags.update({"text_instruction_present", "manual_review_required"})
    if _is_false(cross_image.get("same_object")):
        flags.update({"wrong_object", "claim_mismatch", "manual_review_required"})
    if history and str(history.get("history_flags", "")).strip():
        flags.add("user_history_risk")
    if claim_status == "contradicted":
        flags.add("claim_mismatch")
    return "none" if not flags else ";".join(sorted(flags))


def build_justification(status_reason, supporting_ids, evidence_reason, evidence_met):
    ids = ";".join(supporting_ids) if supporting_ids else "none"
    if evidence_met:
        return f"{status_reason} Supporting images: {ids}."
    return f"{evidence_reason}"


def apply_policy(perception, row, history, pregate_injection, image_ids, image_count):
    extracted = perception.get("extracted_claim") or {}
    per_image = perception.get("per_image") or []
    cross_image = perception.get("cross_image_consistency") or {}

    raw_part = extracted.get("object_part", "unknown")
    cleaned_part = _clean_object_part(raw_part, row["claim_object"])
    extracted = {**extracted, "object_part": cleaned_part}

    evidence_met, evidence_reason = compute_evidence_standard_met(
        row["claim_object"], extracted, per_image, cross_image, image_count)

    valid_image = derive_valid_image(per_image)

    if not evidence_met:
        return {
            "evidence_standard_met": "false",
            "evidence_standard_met_reason": evidence_reason,
            "risk_flags": merge_risk_flags(pregate_injection, history, cross_image, "not_enough_information", per_image),
            "issue_type": _canonical_issue(extracted.get("issue_type", "unknown")),
            "object_part": cleaned_part,
            "claim_status": "not_enough_information",
            "claim_status_justification": build_justification(evidence_reason, [], evidence_reason, False),
            "supporting_image_ids": "none",
            "valid_image": "true" if valid_image else "false",
            "severity": "unknown",
        }

    status, status_reason, supporting = derive_claim_status(extracted, per_image, cross_image, row["claim_object"])

    id_map = {_norm(i): i for i in image_ids}
    supporting = [id_map[_norm(s)] for s in supporting if _norm(s) in id_map]

    severity = derive_severity(extracted, per_image, status)
    risk_flags = merge_risk_flags(pregate_injection, history, cross_image, status, per_image)

    agg_issue = _canonical_issue(extracted.get("issue_type", "unknown"))
    agg_part = cleaned_part
    for img in per_image:
        vi = img.get("visible_issue", "")
        vp = _norm(img.get("visible_part", ""))
        if vi and _norm(vi) not in ("unknown", ""):
            agg_issue = _canonical_issue(vi)
        if vp and vp not in ("unknown", ""):
            agg_part = img.get("visible_part", agg_part)

    # valid_image=false forces not_enough_information regardless of status just computed
    if not valid_image:
        status = "not_enough_information"
        supporting = []
        severity = "unknown"

    return {
        "evidence_standard_met": "true",
        "evidence_standard_met_reason": evidence_reason,
        "risk_flags": risk_flags,
        "issue_type": agg_issue,
        "object_part": agg_part,
        "claim_status": status,
        "claim_status_justification": build_justification(status_reason, supporting, evidence_reason, True),
        "supporting_image_ids": "none" if status == "not_enough_information" or not supporting else ";".join(dict.fromkeys(supporting)),
        "valid_image": "true" if valid_image else "false",
        "severity": severity,
    }