# Multi-Modal Evidence Review — Solution

Pipeline that verifies damage claims (car / laptop / package) using submitted images, claim conversation, user history, and evidence requirements. Produces structured CSV predictions , built as part of hackerrank orchestrate june'26 challenge.

## Architecture

Two-stage design (not agentic):

1. **Perception (VLM)** — one Groq vision call per claim returns structured JSON only (what is visible in images, extracted claim fields, cross-image consistency). No verdict.
2. **Policy (deterministic)** — `policy.py` derives `claim_status`, `evidence_standard_met`, `severity`, etc. from perception + CSV context.
3. **Validation** — `validators.py` enforces enum constraints and cross-field consistency.

```
CSV row → load images → pregate (injection scan) → Groq Llama 4 Scout → policy → validators → output row
```

**Model:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq (multimodal, JSON mode).

## Setup

From the repo root (parent of `code/`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r code/requirements.txt
copy code\.env.example code\.env
```

Edit `code/.env` and set `GROQ_API_KEY` ([Groq console](https://console.groq.com/keys)).

Optional env vars:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Vision model ID |
| `IMAGE_MAX_EDGE` | `768` | Long-edge resize before API (saves tokens) |
| `IMAGE_JPEG_QUALITY` | `75` | JPEG compression quality |
| `USE_PERCEPTION_CACHE` | `1` | Cache VLM JSON under `code/.cache/perceptions/` |
| `GROQ_MAX_RETRIES` | `6` | Retries on 429 rate limits |

## Run predictions

All commands assume `code/` as the working directory and that `dataset/` sits one level above (`../dataset/`).

```powershell
cd code

# Sample set (20 rows, has gold labels for eval)
python main.py --input sample_claims.csv --output ..\dataset\output_sample.csv --sleep 5

# Test set (44 rows — submission output)
python main.py --input claims.csv --output ..\dataset\output.csv --sleep 5

# Mock run (no API calls)
python main.py --input sample_claims.csv --output ..\dataset\output_mock.csv --mock --limit 3
```

### CLI flags

| Flag | Description |
|------|-------------|
| `--input` | CSV filename under `dataset/` (default: `claims.csv`) |
| `--output` | Output CSV path (default: `../dataset/output.csv`) |
| `--sleep` | Seconds between API calls (default: `1.0`) |
| `--limit N` | Process first N rows only |
| `--resume` | Skip rows already present in `--output` without errors |
| `--mock` | Skip VLM; emit placeholder rows |

### Rate limits

Groq free tier has a daily token cap (~500K TPD). Images dominate cost. Tips:

- Use `--resume` after partial runs
- Perception cache keys on `user_id + hash(image_paths|user_claim|claim_object)` so repeated `user_id` values across different cases do not collide
- Lower `IMAGE_MAX_EDGE` if needed (512 saves more tokens)
- On 429, the client parses Groq’s retry-after and waits automatically

## Evaluation

Compare sample predictions against gold labels in `dataset/sample_claims.csv`:

```powershell
cd code/evaluation
python run_eval.py
```

Reports exact-match accuracy for `claim_status`, `issue_type`, `object_part`, `severity`, `evidence_standard_met`, `valid_image`, and per-row set F1 for `risk_flags` and `supporting_image_ids`.

## Project layout

```
code/
├── main.py              # CLI entry point
├── pipeline.py          # Orchestrates load → perceive → policy → validate
├── groq_client.py       # Groq vision API client
├── policy.py            # Deterministic verdict logic
├── validators.py        # Enum repair + hard gates
├── image_loader.py      # Decode/resize images (JPEG, PNG, AVIF, …)
├── pregate.py           # Conversation injection regex scan
├── prompt_builder.py    # User message assembly
├── prompts/
│   └── system_prompt.txt
├── config.py            # Enums and paths
├── io_utils.py          # CSV read/write
├── requirements.txt
├── .env.example
└── evaluation/
    ├── run_eval.py
    └── metrics.py
```

## Key design choices

- **Images resized to 768px** long edge before base64 upload to reduce vision token cost without losing damage detail.
- **`valid_image=false`** when `is_likely_stock_or_edited=true` (e.g. watermarked stock photos); contradicted claims can still be evaluated.
- **Policy handles severity mismatch** (e.g. user claims “pretty bad” but image shows minor scratch → `contradicted`).
- **Injection backstop** — image/chat text instructing “approve” is flagged and blocks auto-approval.
