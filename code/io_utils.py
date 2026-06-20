import pandas as pd
from pathlib import Path
from config import DATASET, OUTPUT_COLUMNS

def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATASET / name, dtype=str).fillna("")

def load_user_history() -> dict:
    df = load_csv("user_history.csv")
    return {r["user_id"]: r.to_dict() for _, r in df.iterrows()}

def load_evidence_requirements() -> list[dict]:
    return load_csv("evidence_requirements.csv").to_dict("records")

def write_output(rows: list[dict], path: Path):
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df.to_csv(path, index=False, quoting=1)