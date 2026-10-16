"""Prompt-injection detection.

Approach: Unicode/leetspeak normalisation + weighted regex rules for known attack families.
Rule weights are combined with noisy-OR:  score = 1 - prod(1 - w_i).
  score >= block threshold -> BLOCK   |  score >= flag threshold -> FLAG   |  else ALLOW
Limitations: rules only know phrasings we thought of; no semantic understanding, so
paraphrases in other languages, homoglyph attacks (Cyrillic letters) and attacks hidden in
retrieved documents are missed, and benign sentences that reuse attack phrasing are blocked.
"""
import re
import unicodedata
from dataclasses import dataclass, field

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

_W = r"(?:\W+\w+)"
RULES = [
    ("instruction_override", 0.80,
     rf"\b(?:ignore|disregard|forget|override|discard)\b{_W}{{0,4}}?\W+(?:previous|prior|above|earlier|preceding|all|any|your|the|these)\b"
     rf"{_W}{{0,3}}?\W+(?:instructions?|rules?|prompts?|guidelines?|directives?|restrictions?|programming)\b"),
    ("instruction_override_told", 0.75,
     r"\b(?:ignore|disregard|forget)\W+(?:everything|anything|what|whatever)\W+(?:you\W+(?:were|have\W+been|are)\W+)?(?:told|instructed|taught|programmed)\b"),
    ("prompt_extraction", 0.80,
     rf"\b(?:reveal|show|print|repeat|display|output|leak|dump|tell\W+me|give\W+me|share)\b{_W}{{0,4}}?\W+"
     r"(?:system|initial|hidden|original|secret|internal)\W+(?:prompt|instructions?|message|configuration|rules)\b"),
    ("role_hijack_strong", 0.75,
     r"\b(?:unrestricted|unfiltered|uncensored|jailbroken)\W+(?:ai|assistant|mode|model)\b|\bdeveloper\W+mode\b|\bjailbreak(?:ed)?\b"
     r"|\bdo\W+anything\W+now\b|(?-i:\bDAN\b)"),
    ("role_change_soft", 0.50, r"\byou\W+are\W+now\b|\bpretend\W+(?:to\W+be|you\W+are|that\W+you\W+are)\b"),
    ("restriction_bypass", 0.65,
     r"\b(?:without|no|remove|disable|bypass|turn\W+off)\W+(?:\w+\W+){0,2}?(?:restrictions?|filters?|guardrails?|safety|safeguards?|limitations?|censorship)\b"),
    ("fake_system_delimiter", 0.55,
     r"(?:^|\n)\s*(?:system|assistant|developer)\s*:|<\|?(?:system|im_start|im_end)\|?>|\[\s*(?:system|inst)\s*\]|#{2,}\s*(?:system|instruction)"),
    ("new_instructions", 0.55, r"\b(?:new|updated|revised|real|actual)\W+(?:instructions?|rules?|directives?)\s*[:\-]"),
    ("secret_exfiltration", 0.65,
     rf"\b(?:reveal|show|give|print|tell|send|leak|dump|share|expose)\b{_W}{{0,3}}?\W+"
     r"(?:api\W*keys?|passwords?|secrets?|credentials?|tokens?|private\W+keys?)\b"),
    ("decode_and_execute", 0.60, r"\b(?:decode|decrypt)\b.{0,40}\b(?:and|then)\W+(?:run|execute|follow|obey)\b"),
    ("encoded_payload", 0.35, r"[A-Za-z0-9+/]{40,}={0,2}"),
    ("code_or_sql_payload", 0.60,
     r"\b(?:execute|run)\W+(?:this\W+)?(?:command|shell|script|sql)\b|\bdrop\W+table\b|\bunion\W+select\b|rm\W+-rf"),
    ("indirect_instruction", 0.60,
     r"\b(?:assistant|ai|chatbot|model)\b\W+(?:you\W+)?(?:must|should|shall|will)\W+(?:now\W+)?(?:ignore|disregard|reveal|send|forward|transfer)\b"),
]
_COMPILED = [(n, w, re.compile(p, re.I)) for n, w, p in RULES]


@dataclass
class InjectionResult:
    score: float
    decision: str                      # allow | flag | block
    hits: list = field(default_factory=list)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return re.sub(r"[ \t]+", " ", text)


class PromptInjectionDetector:
    def __init__(self, block_threshold=0.70, flag_threshold=0.40):
        self.block_t, self.flag_t = block_threshold, flag_threshold

    def assess(self, text: str) -> InjectionResult:
        norm = normalise(text)
        views = [norm, norm.translate(_LEET)]
        best = {}
        for view in views:
            for name, weight, rx in _COMPILED:
                if rx.search(view):
                    best[name] = weight
        score = 1.0
        for w in best.values():
            score *= (1 - w)
        score = round(1 - score, 3)
        decision = "block" if score >= self.block_t else "flag" if score >= self.flag_t else "allow"
        return InjectionResult(score, decision, sorted(best))
