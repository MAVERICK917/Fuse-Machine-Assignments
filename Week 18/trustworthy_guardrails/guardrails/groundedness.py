"""Groundedness validation: is every factual claim supported by the reference documents?

Approach (lexical, no extra model):
 1. split the answer into sentences (claims); skip pleasantries / claims with no factual content
 2. COVERAGE: share of the claim's content words found in the best-matching reference document
 3. NUMBERS: every number in the claim must appear in a reference sentence that is about the
    same thing (>= 50% word overlap) - this catches "50,000" borrowed from the wrong fact
 4. NEGATION: the claim and its best-matching reference sentence must agree on negation
A claim is supported only if all three pass; the answer is grounded only if every claim is.
Limitations: it measures word overlap, not meaning. It passes false claims built entirely from
words in the reference (e.g. wrong scope: "transfers to other banks are free") and rejects honest
paraphrases that use new vocabulary (e.g. "three hundred rupees" for "NPR 300").
"""
import re
from dataclasses import dataclass, field

from .text_utils import content_tokens, has_negation, numbers, split_sentences

_PLEASANTRY = re.compile(
    r"^\s*(?:thank|thanks|hello|hi\b|dear|welcome|happy\s+to|glad\s+to|you'?re\s+welcome|sorry|apolog|"
    r"please\s+let\s+us\s+know|is\s+there\s+anything|feel\s+free)", re.I)


@dataclass
class ClaimCheck:
    claim: str
    supported: bool
    coverage: float
    reason: str


@dataclass
class GroundednessResult:
    grounded: bool
    claims: list = field(default_factory=list)

    @property
    def unsupported(self):
        return [c for c in self.claims if not c.supported]


class GroundednessChecker:
    def __init__(self, min_coverage=0.60, number_overlap=0.50):
        self.min_cov, self.num_overlap = min_coverage, number_overlap

    def check(self, answer: str, references: list) -> GroundednessResult:
        ref_sents = []
        doc_tokens = []
        for d in references:
            toks = set()
            for s in split_sentences(d["text"]):
                st = content_tokens(s)
                ref_sents.append((s, st, numbers(s)))
                toks |= st
            doc_tokens.append(toks)

        results = []
        # redaction placeholders such as [PHONE] are not factual content
        answer = re.sub(r"\[[A-Z_]+\]", "", answer)
        for claim in split_sentences(answer):
            toks, nums = content_tokens(claim), numbers(claim)
            if _PLEASANTRY.match(claim) or (len(toks) < 3 and not nums):
                results.append(ClaimCheck(claim, True, 1.0, "non-factual / pleasantry"))
                continue
            coverage = max((len(toks & dt) / len(toks) for dt in doc_tokens), default=0.0) if toks else 1.0
            if coverage < self.min_cov:
                results.append(ClaimCheck(claim, False, coverage, f"low coverage {coverage:.2f}"))
                continue
            bad_num = None
            for n in nums:
                ok = any(n in sn and toks and len(toks & st) / len(toks) >= self.num_overlap
                         for _, st, sn in ref_sents)
                if not ok:
                    bad_num = n
                    break
            if bad_num is not None:
                results.append(ClaimCheck(claim, False, coverage, f"number {bad_num} not supported in context"))
                continue
            best = max(ref_sents, key=lambda r: len(toks & r[1]), default=None)
            if best and has_negation(claim) != has_negation(best[0]):
                results.append(ClaimCheck(claim, False, coverage, "negation conflicts with reference"))
                continue
            results.append(ClaimCheck(claim, True, coverage, "supported"))
        return GroundednessResult(all(r.supported for r in results), results)
