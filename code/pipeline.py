import hashlib
import json
import os
from pathlib import Path

from image_loader import load_images
from prompt_builder import system_prompt, build_user_text
from pregate import scan_conversation_injection
from policy import apply_policy
from validators import repair_policy_output, fallback_row

CACHE_DIR = Path(__file__).parent / ".cache" / "perceptions"

def _use_cache() -> bool:
    return os.getenv("USE_PERCEPTION_CACHE", "1").strip().lower() not in ("0", "false", "no")

def _cache_key(row: dict) -> str:
    """
    Cache key MUST uniquely identify the actual claim content (images + claim text),
    not just user_id, since the same user_id can appear on multiple distinct claims
    in the dataset (e.g. user_004 -> case_004 AND case_010).
    Hash the image_paths + user_claim so identical content still hits cache,
    but distinct claims never collide.
    """
    raw = f"{row.get('image_paths','')}|{row.get('user_claim','')}|{row.get('claim_object','')}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{row['user_id']}_{h}"

def _load_cached_perception(key: str) -> dict | None:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None

def _save_cached_perception(key: str, perception: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(perception), encoding="utf-8")

def process_row(row, history_map, requirements, client):
    images = load_images(row["image_paths"])
    image_ids = [i.image_id for i in images]
    valid = [i for i in images if i.valid]
    hist = history_map.get(row["user_id"])
    pregate_injection = scan_conversation_injection(row.get("user_claim", ""))
    if not valid:
        return fallback_row(row, "No decodable images in submission.")
    if client is None:
        out = fallback_row(row, "Mock mode — no API call.")
        out["valid_image"] = "true"
        return out
    user_text = build_user_text(row, hist, requirements)
    sys_p = system_prompt()
    cache_key = _cache_key(row)

    perception = _load_cached_perception(cache_key) if _use_cache() else None
    if perception:
        print(f"  (perception cache hit: {cache_key})")
    else:
        try:
            perception = client.perceive(sys_p, user_text, [(i.image_id, i.bytes_jpeg) for i in valid])
            if _use_cache():
                _save_cached_perception(cache_key, perception)
        except Exception as e:
            out = fallback_row(row, f"Model error: {e}")
            out["valid_image"] = "true"
            return out

    try:
        policy_out = apply_policy(perception, row, hist, pregate_injection, image_ids, len(valid))
        fixed = repair_policy_output(policy_out, row, image_ids, perception)
        return {"user_id": row["user_id"], "image_paths": row["image_paths"],
                "user_claim": row["user_claim"], "claim_object": row["claim_object"], **fixed}
    except Exception as e:
        out = fallback_row(row, f"Model error: {e}")
        out["valid_image"] = "true"
        return out
