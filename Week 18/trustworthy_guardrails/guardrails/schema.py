"""Output schema validation (standard library only).

The model must return ONE JSON object:
  {"answer": str (1..600 chars), "category": one of CATEGORIES, "confidence": number 0..1,
   "sources": non-empty list of reference ids that were actually provided}
Strict by design: extra fields, wrong types, out-of-range values and unknown sources are rejected.
The only repair we do is stripping a ```json code fence, which models add very often.
Limitation: a response can be perfectly valid JSON and still be wrong or made up (see groundedness).
"""
import json
import re
from dataclasses import dataclass, field

from .config import CATEGORIES

REQUIRED = ("answer", "category", "confidence", "sources")


@dataclass
class SchemaResult:
    valid: bool
    data: dict | None = None
    errors: list = field(default_factory=list)


def _strip_fence(raw: str) -> str:
    m = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw, re.S | re.I)
    return m.group(1) if m else raw


class SchemaValidator:
    def __init__(self, answer_max_chars=600):
        self.max_chars = answer_max_chars

    def validate(self, raw: str, known_source_ids=None) -> SchemaResult:
        try:
            data = json.loads(_strip_fence(raw))
        except (json.JSONDecodeError, TypeError):
            return SchemaResult(False, None, ["not valid JSON"])
        if not isinstance(data, dict):
            return SchemaResult(False, None, ["top-level JSON value must be an object"])
        errors = []
        for key in REQUIRED:
            if key not in data:
                errors.append(f"missing field '{key}'")
        for key in data:
            if key not in REQUIRED:
                errors.append(f"unexpected field '{key}'")
        a = data.get("answer")
        if "answer" in data:
            if not isinstance(a, str):
                errors.append("'answer' must be a string")
            elif not a.strip():
                errors.append("'answer' is empty")
            elif len(a) > self.max_chars:
                errors.append(f"'answer' longer than {self.max_chars} chars")
        if "category" in data and data["category"] not in CATEGORIES:
            errors.append(f"'category' must be one of {list(CATEGORIES)}")
        c = data.get("confidence")
        if "confidence" in data:
            if isinstance(c, bool) or not isinstance(c, (int, float)):
                errors.append("'confidence' must be a number")
            elif not 0.0 <= c <= 1.0:
                errors.append("'confidence' must be between 0 and 1")
        s = data.get("sources")
        if "sources" in data:
            if not isinstance(s, list) or not s or not all(isinstance(x, str) for x in s):
                errors.append("'sources' must be a non-empty list of strings")
            elif known_source_ids is not None:
                unknown = [x for x in s if x not in known_source_ids]
                if unknown:
                    errors.append(f"unknown source ids {unknown}")
        return SchemaResult(not errors, data if not errors else None, errors)
