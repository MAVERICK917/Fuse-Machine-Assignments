"""Small text helpers shared by retrieval and the groundedness checker (standard library only)."""
import re

STOP = set("""a an the is are was were be been being to of in on at for and or but with by from as it its this that
these those can may will you your we our us i me my please thank thanks hello hi regards also if then than so such
there their they them do does did have has had would should could into over per via any all more most up out about
each other which who whom what when where how within am npr rs just very get""".split())

# Tiny synonym map so honest paraphrases ("daily" vs "per day") are not rejected.
SYN = {"daily": "day", "days": "day", "cost": "fee", "costs": "fee", "charge": "fee", "charges": "fee",
       "fees": "fee", "price": "fee", "annum": "year", "yearly": "year", "annual": "year", "years": "year",
       "monthly": "month", "months": "month", "business": "working"}

NEGATIONS = {"not", "no", "never", "cannot", "can't", "won't", "isn't", "aren't", "don't", "doesn't", "without"}

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z][a-z'@.\-]*[a-z]|[a-z]")


def stem(word: str) -> str:
    for suf in ("ing", "ed", "es", "s", "ly"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def numbers(text: str) -> set:
    return {m.replace(",", "").rstrip(".") for m in _NUM.findall(text)}


def words(text: str) -> list:
    return [w.strip(".'-") for w in _WORD.findall(text.lower())]


def content_tokens(text: str) -> set:
    out = set()
    for w in words(_NUM.sub(" ", text)):
        if not w or w in STOP or w in NEGATIONS:
            continue
        out.add(SYN.get(w, stem(w)))
    return out


def has_negation(text: str) -> bool:
    return any(w in NEGATIONS for w in words(text))


def split_sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def retrieve(query: str, docs: list, k: int = 2) -> list:
    """Return up to k docs ranked by content-word overlap with the query (score must be >= 1)."""
    q = content_tokens(query)
    scored = []
    for d in docs:
        score = len(q & content_tokens(d["text"]))
        if score >= 1:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:k]]
