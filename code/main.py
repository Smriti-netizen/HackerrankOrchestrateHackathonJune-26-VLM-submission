import argparse
import json
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from config import DATASET, OUTPUT_COLUMNS
from io_utils import load_csv, load_user_history, load_evidence_requirements, write_output
from pipeline import process_row, _cache_key

def _row_ok(row: dict) -> bool:
    j = str(row.get("claim_status_justification", ""))
    return "Model error" not in j and row.get("issue_type", "unknown") != "unknown"


def _load_resume_rows(path: Path) -> dict[str, dict]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return {_cache_key(r.to_dict()): r.to_dict() for _, r in df.iterrows() if _row_ok(r.to_dict())}


def main():
    load_dotenv(Path(__file__).parent / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="claims.csv")
    parser.add_argument("--output", default=str(DATASET / "output.csv"))
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true",
                        help="Reuse successful rows from existing --output file (0 API calls for those)")
    args = parser.parse_args()
    df = load_csv(args.input)
    if args.limit > 0:
        df = df.head(args.limit)
    history = load_user_history()
    reqs = load_evidence_requirements()
    out_path = Path(args.output)
    cached_out = _load_resume_rows(out_path) if args.resume else {}

    if args.mock:
        client = None
    else:
        from groq_client import GroqClient
        client = GroqClient()

    rows = []
    api_calls = skipped = 0
    for i, (_, row) in enumerate(df.iterrows(), 1):
        row_dict = row.to_dict()
        key = _cache_key(row_dict)
        print(f"[{i}/{len(df)}] {row_dict['user_id']}", end="")
        if key in cached_out:
            rows.append({c: cached_out[key].get(c, "") for c in OUTPUT_COLUMNS})
            skipped += 1
            print(" (resume — skipped)")
            continue
        print()
        rows.append(process_row(row_dict, history, reqs, client))
        api_calls += 1
        if client and args.sleep > 0:
            time.sleep(args.sleep)
    write_output(rows, out_path)
    print(f"Wrote {out_path} ({api_calls} API calls, {skipped} resumed from disk)")
if __name__ == "__main__":
    main()