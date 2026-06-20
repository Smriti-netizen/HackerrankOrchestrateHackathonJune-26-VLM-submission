import re

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"mark\s+(it\s+)?supported",
    r"approve\s+(the\s+)?claim",
    r"skip\s+review",
    r"bypass\s+review",
    r"do\s+not\s+review",
    r"auto\s*approve",
]

def scan_conversation_injection(user_claim: str) -> bool:
    text = (user_claim or "").lower()
    return any(re.search(p, text) for p in INJECTION_PATTERNS)