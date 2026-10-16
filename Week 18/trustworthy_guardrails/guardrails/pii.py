"""PII detection and redaction (used on user input AND on model output).

Approach: ordered regex patterns + validators (Luhn for cards, context words for IDs/accounts),
overlap resolution, and an allow-list for public contact details that are not private data.
Limitations: no NER (names/addresses are not detected), no obfuscation handling
("ram at gmail dot com", spelled-out digits), and number-shaped IDs can look like phone numbers.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    type: str
    start: int
    end: int
    text: str


def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _key(s: str) -> str:
    return re.sub(r"[^0-9a-z@.]", "", s.lower())


# (type, compiled regex, group index holding the sensitive span, optional validator)
_PATTERNS = [
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), 0, luhn_ok),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), 0, None),
    ("CITIZENSHIP_NO", re.compile(r"(?<!\d)\d{2}-\d{2}-\d{2}-\d{4,5}(?!\d)"), 0, None),
    ("ID_NUMBER", re.compile(
        r"\b(?:citizenship|nid|national\s*id|pan|passport|licen[sc]e)\s*(?:no\.?|number|num|#|card)?\s*(?:is|:|-)?\s*"
        r"([A-Z]{0,2}\d[\dA-Z-]{5,14})\b", re.I), 1, None),
    ("ACCOUNT_NO", re.compile(
        r"\b(?:a/?c|account)\s*(?:no\.?|number|num|#)?\s*(?:is|:|-)?\s*(\d{9,18})\b", re.I), 1, None),
    ("PHONE", re.compile(r"(?<![\d-])(?:\+?977[-\s]?)?9[78]\d{8}(?!\d)"), 0, None),   # Nepali mobile
    ("PHONE", re.compile(r"(?<![\d-])01[-\s]?\d{6,7}(?!\d)"), 0, None),               # Kathmandu landline
]


class PIIDetector:
    def __init__(self, allowlist=()):
        self.allow = {_key(a) for a in allowlist}

    def detect(self, text: str) -> list:
        accepted = []
        for ptype, rx, grp, validator in _PATTERNS:
            for m in rx.finditer(text):
                span_text = m.group(grp)
                if validator and not validator(span_text):
                    continue
                if _key(span_text) in self.allow:
                    continue
                s, e = m.span(grp)
                if any(not (e <= f.start or s >= f.end) for f in accepted):
                    continue  # overlaps a higher-priority finding
                accepted.append(Finding(ptype, s, e, span_text))
        return sorted(accepted, key=lambda f: f.start)

    @staticmethod
    def redact(text: str, findings: list) -> str:
        for f in sorted(findings, key=lambda f: f.start, reverse=True):
            text = text[: f.start] + f"[{f.type}]" + text[f.end:]
        return text

    def scan(self, text: str):
        findings = self.detect(text)
        return self.redact(text, findings), findings
