"""Runs every test case, writes results/test_results.{csv,md} and results/metrics.json,
and prints a summary. Usage:  python tests/run_evaluation.py"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guardrails import GuardedAssistant, load_kb                      # noqa: E402
from guardrails.config import Config                                  # noqa: E402
from guardrails.groundedness import GroundednessChecker               # noqa: E402
from guardrails.injection import PromptInjectionDetector              # noqa: E402
from guardrails.leaks import LeakDetector                             # noqa: E402
from guardrails.pii import PIIDetector                                # noqa: E402
from guardrails.schema import SchemaValidator                         # noqa: E402
from guardrails.topics import SensitiveTopicClassifier                # noqa: E402
from cases import CASES, SCRIPTS                                      # noqa: E402

CFG = Config()
KB = load_kb()
KB_BY_ID = {d["id"]: d for d in KB}
pii = PIIDetector(CFG.public_contacts)
inj = PromptInjectionDetector(CFG.injection_block_threshold, CFG.injection_flag_threshold)
topics = SensitiveTopicClassifier()
schema = SchemaValidator(CFG.answer_max_chars)
grounded = GroundednessChecker(CFG.groundedness_min_coverage, CFG.number_context_min_overlap)
leaks = LeakDetector(CFG.canary)


def run_case(c):
    """Returns (actual_value, actual_text, pred_positive, passed)."""
    k, inp = c["kind"], c["input"]
    refs = [KB_BY_ID[i] for i in c["refs"]]
    if k == "pii":
        scan, found = pii.scan(inp)
        actual = bool(found)
        return actual, f"flagged={actual} types={sorted({f.type for f in found})} -> \"{scan}\"", actual, actual == c["expected"]
    if k == "injection":
        r = inj.assess(inp)
        return r.decision, f"{r.decision} (score {r.score}, rules {r.hits})", r.decision != "allow", r.decision == c["expected"]
    if k == "topic":
        r = topics.classify(inp)
        return r.category, f"category={r.category} action={r.action}", r.category is not None, r.category == c["expected"]
    if k == "schema":
        r = schema.validate(inp, {d["id"] for d in refs})
        return r.valid, f"valid={r.valid} {r.errors}", not r.valid, r.valid == c["expected"]
    if k == "grounded":
        r = grounded.check(inp, refs)
        why = [f"{x.reason}" for x in r.unsupported]
        return r.grounded, f"grounded={r.grounded} {why}", not r.grounded, r.grounded == c["expected"]
    if k == "output":
        scan, found = pii.scan(inp)
        lk = leaks.scan(inp)
        actual = bool(found or lk)
        return actual, f"flagged={actual} pii={sorted({f.type for f in found})} leaks={lk}", actual, actual == c["expected"]
    if k == "e2e":
        bot = GuardedAssistant(llm=SCRIPTS[c.get("script", "default")], kb=KB, config=CFG)
        r = bot.handle(inp)
        blob = r.message + json.dumps(bot.audit.entries)
        ok = r.status == c["expected"]
        ok &= all(s in r.message for s in c.get("expect_contains", []))
        ok &= not any(s in blob for s in c.get("expect_absent", []))
        if "expect_stage" in c:
            ok &= any(t.get("stage") == c["expect_stage"] for t in r.trace)
        ok &= bot.audit.verify()
        return r.status, f"status={r.status} | \"{r.message[:90]}\"", None, ok
    raise ValueError(k)


def confusion(rows):
    tp = sum(1 for r in rows if r["label"] and r["pred"])
    fp = sum(1 for r in rows if not r["label"] and r["pred"])
    fn = sum(1 for r in rows if r["label"] and not r["pred"])
    tn = sum(1 for r in rows if not r["label"] and not r["pred"])
    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * rc / (p + rc) if p and rc else (0.0 if p is not None and rc is not None else None)
    return dict(n=len(rows), TP=tp, FP=fp, FN=fn, TN=tn,
                precision=None if p is None else round(p, 3), recall=None if rc is None else round(rc, 3),
                f1=None if f1 is None else round(f1, 3))


def main():
    results, by_guard = [], defaultdict(list)
    for c in CASES:
        actual, text, pred, passed = run_case(c)
        row = dict(id=c["id"], guardrail=c["guardrail"], description=c["desc"], input=c["input"].replace("\n", " ⏎ "),
                   reference=",".join(c["refs"]), expected=str(c["expected"]), actual=text, status="PASS" if passed else "FAIL")
        results.append(row)
        if c["label"] is not None:
            by_guard[c["guardrail"]].append(dict(label=c["label"], pred=pred, id=c["id"]))

    metrics = {g: confusion(rows) for g, rows in by_guard.items()}
    allrows = [r for rows in by_guard.values() for r in rows]
    metrics["ALL_LABELLED"] = confusion(allrows)
    metrics["_summary"] = dict(total=len(results), passed=sum(r["status"] == "PASS" for r in results),
                               failed=[r["id"] for r in results if r["status"] == "FAIL"],
                               false_positives=[r["id"] for r in allrows if not r["label"] and r["pred"]],
                               false_negatives=[r["id"] for r in allrows if r["label"] and not r["pred"]])

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    with open(out / "test_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader(); w.writerows(results)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    esc = lambda s: str(s).replace("|", "\\|")
    md = ["| ID | Guardrail | Test input | Reference | Expected | Actual | Status |", "|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['id']} | {r['guardrail']} | {esc(r['input'][:90])} | {r['reference'] or '-'} | {esc(r['expected'])} | {esc(r['actual'][:110])} | {r['status']} |")
    (out / "test_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    s = metrics["_summary"]
    print(f"\nPASSED {s['passed']}/{s['total']}   FAILED: {s['failed']}")
    print(f"False positives: {s['false_positives']}\nFalse negatives: {s['false_negatives']}\n")
    print(f"{'guardrail':18} {'n':>3} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'prec':>6} {'recall':>6} {'f1':>6}")
    for g, m in metrics.items():
        if g.startswith("_"):
            continue
        print(f"{g:18} {m['n']:>3} {m['TP']:>3} {m['FP']:>3} {m['FN']:>3} {m['TN']:>3} {str(m['precision']):>6} {str(m['recall']):>6} {str(m['f1']):>6}")
    for r in results:
        if r["status"] == "FAIL":
            print(f"\n[FAIL] {r['id']} {r['description']}\n   expected: {r['expected']}\n   actual:   {r['actual']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
