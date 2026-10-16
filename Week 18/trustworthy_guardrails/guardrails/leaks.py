"""Secret / system-prompt leak detection for model OUTPUT.

Looks for: the canary token planted in the system prompt, distinctive system-prompt phrases,
API keys, private keys, 'password is ...' patterns and internal IP addresses.
PII (emails, phones, IDs) is handled separately by PIIDetector.
Limitation: pattern based - a paraphrased or translated leak of the system prompt is not caught.
"""
import re


class LeakDetector:
    def __init__(self, canary: str):
        self.canary = canary
        self.patterns = [
            ("API_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b|\bAKIA[0-9A-Z]{16}\b")),
            ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
            ("CREDENTIAL", re.compile(r"\b(?:password|passwd|api[_ -]?key|secret)\s*(?:is|:|=)\s*\S+", re.I)),
            ("INTERNAL_IP", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
            ("PROMPT_PHRASE", re.compile(r"never\s+reveal\s+these\s+instructions|answer\s+ONLY\s+from\s+the\s+reference\s+documents", re.I)),
        ]

    def scan(self, text: str) -> list:
        found = []
        if self.canary.lower() in text.lower():
            found.append("CANARY")
        for name, rx in self.patterns:
            if rx.search(text):
                found.append(name)
        return found
