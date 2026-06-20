import base64
import json
import os
import re
import time

from groq import Groq

def _retry_wait_seconds(err: str) -> float:
    """Parse Groq 429 message: 'Please try again in 19m8.6016s'."""
    m = re.search(r"try again in (\d+)m([\d.]+)s", err, re.I)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.search(r"try again in ([\d.]+)s", err, re.I)
    if m:
        return float(m.group(1))
    return 60.0

def _is_rate_limit(err: str) -> bool:
    e = err.lower()
    return "429" in err or "rate_limit" in e or "rate limit" in e

PERCEPTION_SCHEMA_HINT = """
Return a single JSON object with exactly these keys:
- extracted_claim: {object_part, issue_type, severity_wording}
- per_image: array of {image_id, object_type, visible_part, visible_issue, damage_visible,
  quality_flags, text_instruction_present, is_likely_stock_or_edited, notes}
- cross_image_consistency: {same_object, notes}
"""


class GroqClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to code/.env — get a key at https://console.groq.com/keys"
            )
        self.client = Groq(api_key=api_key)
        self.model = os.getenv(
            "GROQ_MODEL",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        )
        print(f"Using Groq model: {self.model}")

    def perceive(self, system: str, user_text: str, images: list[tuple[str, bytes]]) -> dict:
        content: list[dict] = [{"type": "text", "text": user_text}]
        for img_id, data in images:
            content.append({"type": "text", "text": f"[Image ID: {img_id}]"})
            b64 = base64.standard_b64encode(data).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        full_system = system.strip() + "\n\n" + PERCEPTION_SCHEMA_HINT
        max_retries = int(os.getenv("GROQ_MAX_RETRIES", "6"))

        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": content},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content
                if not raw:
                    raise ValueError("Groq returned empty response")
                return json.loads(raw)
            except Exception as e:
                last_err = e
                err = str(e)
                if _is_rate_limit(err) and attempt < max_retries - 1:
                    wait = min(_retry_wait_seconds(err), float(os.getenv("GROQ_MAX_RETRY_WAIT", "1200")))
                    print(f"  Rate limited — waiting {wait:.0f}s then retry ({attempt + 1}/{max_retries})...")
                    time.sleep(wait + 2)
                    continue
                raise
        raise last_err or RuntimeError("Groq perceive failed")
