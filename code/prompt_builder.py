from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"

def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")

def build_user_text(row: dict, history: dict | None, requirements: list[dict]) -> str:
    obj = row["claim_object"]
    reqs = [r for r in requirements if r["claim_object"] in (obj, "all")]
    checklist = "\n".join(
        f"- [{r['requirement_id']}] {r['applies_to']}: {r['minimum_image_evidence']}"
        for r in reqs
    )
    hist = "No history on file."
    if history:
        hist = (
            f"past_claim_count={history.get('past_claim_count','')}; "
            f"rejected={history.get('rejected_claim','')}; "
            f"last_90_days={history.get('last_90_days_claim_count','')}; "
            f"flags={history.get('history_flags','')}; "
            f"summary={history.get('history_summary','')}"
        )
    return f"""claim_object: {obj}

CONVERSATION:
{row['user_claim']}

EVIDENCE CHECKLIST:
{checklist}

USER HISTORY (risk context only):
{hist}

Inspect each labeled image and report observations only."""