import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from metrics import accuracy, set_f1

EXACT = ["claim_status", "issue_type", "object_part", "severity", "evidence_standard_met", "valid_image"]
SET_FIELDS = ["risk_flags", "supporting_image_ids"]

def main():
    repo = Path(__file__).resolve().parents[2]
    gold = pd.read_csv(repo / "dataset" / "sample_claims.csv", dtype=str).fillna("")
    pred = pd.read_csv(repo / "dataset" / "output_sample.csv", dtype=str).fillna("")
    m = gold.merge(pred, on="user_id", suffixes=("_gold", "_pred"))
    print(f"Rows: {len(m)}\n")
    for f in EXACT:
        print(f"{f}: {accuracy(m[f'{f}_pred'].tolist(), m[f'{f}_gold'].tolist()):.1%}")
    print()
    for f in SET_FIELDS:
        scores = [set_f1(p, g) for p, g in zip(m[f"{f}_pred"], m[f"{f}_gold"])]
        print(f"{f} per-row F1: {sum(scores)/len(scores):.1%}")

if __name__ == "__main__":
    main()