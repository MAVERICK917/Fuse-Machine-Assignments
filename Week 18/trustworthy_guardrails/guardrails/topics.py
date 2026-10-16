"""Sensitive-topic classification with a per-category action.

Approach: priority-ordered keyword/phrase rules (first matching category wins).
Limitations: keyword matching has no context. It refuses harmless questions that mention a
topic ("how does the bank detect money laundering?") and misses indirect or euphemistic
wording ("I just want everything to stop"). English only.
"""
import re
from dataclasses import dataclass

# (category, action, regex) in priority order
_RULES = [
    ("self_harm", "crisis_response",
     r"\b(?:kill\W+myself|end\W+(?:my\W+life|it\W+all)|suicid\w*|want\W+to\W+die|don'?t\W+want\W+to\W+live|hurt\W+myself|self[- ]?harm)\b"),
    ("illegal_activity", "refuse",
     r"\b(?:launder\w*|evade\W+(?:tax|kyc|aml)|avoid\W+(?:kyc|aml)|bypass\W+(?:kyc|aml)|fake\W+(?:documents?|citizenship|id|passport|salary)|forg(?:e|ed|ing)\b|hawala|hundi|hide\W+(?:money|income)\W+from|terror\w*\W+financ\w*)"),
    ("third_party_access", "refuse",
     r"\b(?:balance|statement|transactions?|account\W+details?|password|pin|otp)\b.{0,25}\b(?:of|for)\W+(?:my\W+)?"
     r"(?:husband|wife|neighbou?r|friend|ex|boss|colleague|someone|another\W+person|his|her|their)\b"
     r"|\b(?:someone|somebody|another\W+person|his|her)\W+(?:else'?s?\W+)?(?:account|balance|pin|otp|password)\b"),
    ("legal_advice", "allow_with_disclaimer",
     r"\b(?:sue|lawsuit|legal\W+action|court\W+case|am\W+i\W+liable|legally\W+(?:required|liable)|lawyer|attorney)\b"),
    ("investment_advice", "allow_with_disclaimer",
     r"\b(?:should\W+i\W+(?:invest|buy|sell)|which\W+(?:stock|share|mutual\W+fund)|best\W+(?:stock|investment)|guaranteed\W+returns?|crypto(?:currency)?|bitcoin)\b"),
]
_COMPILED = [(c, a, re.compile(p, re.I)) for c, a, p in _RULES]


@dataclass
class TopicResult:
    category: str | None
    action: str            # allow | crisis_response | refuse | allow_with_disclaimer


class SensitiveTopicClassifier:
    def classify(self, text: str) -> TopicResult:
        for category, action, rx in _COMPILED:
            if rx.search(text):
                return TopicResult(category, action)
        return TopicResult(None, "allow")
