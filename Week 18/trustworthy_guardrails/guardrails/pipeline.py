"""GuardedAssistant: wires input guardrails -> retrieval -> LLM -> output guardrails.

INPUT  (before the model):  size -> PII redaction -> prompt-injection -> sensitive topic
OUTPUT (after the model):   leak/secret scan -> schema -> PII/sensitive redaction -> groundedness
Invalid output handling:    secret leak = block + fallback | schema/groundedness fail = regenerate
                            once, then safe fallback | PII in output = redact | no source = fallback
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .audit import AuditLog
from .config import MESSAGES, Config
from .groundedness import GroundednessChecker
from .injection import PromptInjectionDetector
from .leaks import LeakDetector
from .llm import HARDENING_NOTE, SYSTEM_PROMPT_TEMPLATE, mock_llm
from .pii import PIIDetector
from .schema import SchemaValidator
from .text_utils import retrieve
from .topics import SensitiveTopicClassifier

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"


def load_kb(path=KB_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class GuardedResult:
    status: str                      # answered | refused | crisis | fallback
    message: str
    data: dict | None = None
    trace: list = field(default_factory=list)


class GuardedAssistant:
    def __init__(self, llm=mock_llm, kb=None, config: Config | None = None, audit: AuditLog | None = None):
        self.cfg = config or Config()
        self.llm, self.kb = llm, (kb if kb is not None else load_kb())
        self.audit = audit or AuditLog()
        self.pii = PIIDetector(allowlist=self.cfg.public_contacts)
        self.injection = PromptInjectionDetector(self.cfg.injection_block_threshold, self.cfg.injection_flag_threshold)
        self.topics = SensitiveTopicClassifier()
        self.schema = SchemaValidator(self.cfg.answer_max_chars)
        self.grounded = GroundednessChecker(self.cfg.groundedness_min_coverage, self.cfg.number_context_min_overlap)
        self.leaks = LeakDetector(self.cfg.canary)

    # ------------------------------------------------------------------
    def _finish(self, status, message, trace, data=None):
        self.audit.record("response", {"status": status, "trace": trace})
        return GuardedResult(status, message, data, trace)

    def handle(self, user_text: str) -> GuardedResult:
        trace = []

        # ---------------- INPUT GUARDRAILS ----------------
        if len(user_text) > self.cfg.max_input_chars:
            trace.append({"stage": "input.size", "action": "block"})
            return self._finish("refused", MESSAGES["refuse_too_long"], trace)

        clean, findings = self.pii.scan(user_text)            # 1) PII: redact, continue
        if findings:
            trace.append({"stage": "input.pii", "action": "redact", "types": sorted({f.type for f in findings})})
        self.audit.record("request", {"text": clean})         # only redacted text is logged

        inj = self.injection.assess(clean)                     # 2) injection: block / flag
        trace.append({"stage": "input.injection", "action": inj.decision, "score": inj.score, "hits": inj.hits})
        if inj.decision == "block":
            return self._finish("refused", MESSAGES["refuse_injection"], trace)

        topic = self.topics.classify(clean)                    # 3) sensitive topic: per-category action
        trace.append({"stage": "input.topic", "category": topic.category, "action": topic.action})
        if topic.action == "crisis_response":
            return self._finish("crisis", MESSAGES["crisis"], trace)
        if topic.action == "refuse":
            return self._finish("refused", MESSAGES["refuse_topic"], trace)
        disclaimer = {"legal_advice": MESSAGES["disclaimer_legal"],
                      "investment_advice": MESSAGES["disclaimer_investment"]}.get(topic.category, "")

        # ---------------- RETRIEVAL + MODEL ----------------
        docs = retrieve(clean, self.kb)
        if not docs:
            trace.append({"stage": "retrieval", "action": "no_reference_found"})
            return self._finish("fallback", (MESSAGES["fallback"] + " " + disclaimer).strip(), trace)

        system = SYSTEM_PROMPT_TEMPLATE.format(canary=self.cfg.canary)
        if inj.decision == "flag":
            system += HARDENING_NOTE
        known_ids = {d["id"] for d in docs}

        # ---------------- OUTPUT GUARDRAILS ----------------
        for attempt in range(self.cfg.max_regenerations + 1):
            raw = self.llm(system, clean, docs, attempt)

            leaked = self.leaks.scan(raw)                      # 1) secrets / system-prompt leak: never retry
            if leaked:
                trace.append({"stage": "output.leak", "action": "block", "types": leaked})
                return self._finish("fallback", MESSAGES["fallback"], trace)

            sr = self.schema.validate(raw, known_ids)          # 2) schema
            if not sr.valid:
                trace.append({"stage": "output.schema", "action": "regenerate", "attempt": attempt, "errors": sr.errors})
                continue

            answer, out_findings = self.pii.scan(sr.data["answer"])   # 3) PII in output: redact
            if out_findings:
                trace.append({"stage": "output.pii", "action": "redact", "types": sorted({f.type for f in out_findings})})
                sr.data["answer"] = answer

            gr = self.grounded.check(answer, docs)             # 4) groundedness
            if not gr.grounded:
                trace.append({"stage": "output.groundedness", "action": "regenerate", "attempt": attempt,
                              "unsupported": [{"claim": c.claim, "reason": c.reason} for c in gr.unsupported]})
                continue

            trace.append({"stage": "output.ok", "attempt": attempt})
            return self._finish("answered", (answer + " " + disclaimer).strip(), trace, sr.data)

        trace.append({"stage": "output.exhausted", "action": "safe_fallback"})
        return self._finish("fallback", (MESSAGES["fallback"] + " " + disclaimer).strip(), trace)
