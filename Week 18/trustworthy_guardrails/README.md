# Input & Output Guardrails for a Bank Support Assistant

Trustworthy AI assignment (Week 18). A runnable, dependency-free implementation of **input guardrails**
(PII, prompt injection, sensitive topics) and **output guardrails** (schema, groundedness, sensitive-information
detection) around a small RAG-style assistant for a fictional bank, *Everest Digital Bank*.

Follows the reference repo's approach (`kss_trustworthy_ai`): pure Python standard library, defense in depth,
audit logging, and a test suite that proves the behaviour.

## Quick start
```bash
# Python 3.10+ ; no pip install needed
python app.py --demo                       # scripted examples with the guardrail trace
python app.py                              # interactive chat
python tests/run_evaluation.py             # all 85 test cases + precision/recall -> results/
python -m unittest discover -s tests -v    # same cases as unit tests
```

## Project layout
```
guardrails/
  config.py        thresholds, canned messages, public contact allow-list
  pii.py           PII detection + redaction (regex, Luhn, context words, allow-list)
  injection.py     prompt-injection detector (weighted rules, noisy-OR score)
  topics.py        sensitive-topic classifier + per-category action
  schema.py        output schema validation
  groundedness.py  claim-level groundedness check (coverage, numbers, negation)
  leaks.py         secret / system-prompt leak detection (canary token etc.)
  audit.py         hash-chained, tamper-evident audit log
  llm.py           deterministic mock LLM + system prompt (swap in a real model here)
  pipeline.py      GuardedAssistant: wires everything together
data/knowledge_base.json     7 bank policy documents used as reference information
tests/cases.py               85 test cases (input, reference, expected, label)
tests/run_evaluation.py      runs cases, writes results/test_results.csv|md, metrics.json
tests/test_guardrails.py     unittest wrapper
docs/architecture.svg|png    architecture diagram
REPORT.md                    evaluation report (design, results, failures, trade-offs, risks)
```

## Usage example
```python
from guardrails import GuardedAssistant
bot = GuardedAssistant()
r = bot.handle("My email is ram@gmail.com. How much does a debit card replacement cost?")
print(r.status, "|", r.message)     # answered | Debit card replacement costs NPR 300.
print(r.trace)                      # [input.pii redact, input.injection allow, ..., output.ok]
```
Statuses: `answered`, `refused`, `crisis`, `fallback`. Every decision is in `r.trace` and in `bot.audit`.

To use a real model, pass any function with this signature (the guardrails do not change):
```python
def my_llm(system: str, user: str, docs: list[dict], attempt: int) -> str:   # must return a JSON string
    ...
bot = GuardedAssistant(llm=my_llm)
```

## What each guardrail does
| Stage | Guardrail | Detection | Action when flagged |
|---|---|---|---|
| Input | Size check | length > 2000 chars | block |
| Input | PII | regex + Luhn + context words, public contacts allow-listed | **redact** (`[EMAIL]`, `[PHONE]`...) and continue |
| Input | Prompt injection | 13 weighted rule families, unicode + leetspeak normalisation, noisy-OR score | score ≥ 0.70 **block**; 0.40-0.70 **flag** (hardened prompt); else allow |
| Input | Sensitive topics | priority-ordered keyword rules | self-harm → **crisis message**; illegal / third-party access → **refuse**; legal / investment → **answer + disclaimer** |
| Output | Leak / secret scan | canary token, API keys, prompt phrases | **block** + safe fallback (never retried) |
| Output | Schema | strict JSON schema (types, enum, range, sources must be provided docs) | **regenerate once**, then fallback |
| Output | PII / sensitive info | same PII detector on the answer | **redact** |
| Output | Groundedness | per-claim word coverage + number-in-context + negation | **regenerate once**, then fallback |

## Design decisions
- **Defense in depth.** No single check is trusted; each one covers a different failure.
- **PII is redacted first**, so the model, the logs and the audit trail only ever see `[EMAIL]`-style placeholders.
- **Block vs flag.** Clear attacks are blocked; ambiguous ones are allowed through with a hardened prompt, because blocking everything ambiguous would reject real customers.
- **Fail closed.** If output cannot be validated, the user gets a safe fallback that points to the helpline, never an unverified answer.
- **Canary token** in the system prompt gives a cheap, near-zero-false-positive signal that the prompt leaked.
- **Standard library only**, so the safety code is small and auditable, and runs anywhere. The trade-off is simple heuristics instead of ML models (see REPORT.md section 4).
- **Mock LLM** keeps the tests deterministic and offline. Output-guardrail tests feed model outputs directly, so they do not depend on any model.

## Evaluation results (from `python tests/run_evaluation.py`)
**72 of 85 cases pass.** The 13 failures are documented limitations (see REPORT.md), not hidden.

| Guardrail | Cases | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| Input: PII detection | 14 | 7 | 1 | 2 | 4 | 0.88 | 0.78 | 0.82 |
| Input: prompt-injection | 17 | 10 | 1 | 2 | 4 | 0.91 | 0.83 | 0.87 |
| Input: sensitive-topic | 11 | 5 | 1 | 2 | 3 | 0.83 | 0.71 | 0.77 |
| Output: schema validation | 11 | 9 | 0 | 0 | 2 | 1.00 | 1.00 | 1.00 |
| Output: groundedness | 11 | 5 | 1 | 1 | 4 | 0.83 | 0.83 | 0.83 |
| Output: sensitive-info / leak | 10 | 6 | 0 | 2 | 2 | 1.00 | 0.75 | 0.86 |
| **All labelled cases** | 74 | 42 | 4 | 9 | 19 | 0.91 | 0.82 | 0.87 |

Positive = "should be flagged/rejected" (PII present, attack, sensitive topic, invalid output, ungrounded claim, leak).
For injection, `flag` and `block` both count as detected. The 11 end-to-end cases are scored pass/fail only.
False positives: P12, I10, T07, G10. False negatives: P13, P14, I11, I12, T08, T11, G09, O09, O10.
The full per-case table (input, reference, expected, actual, pass/fail) is in `results/test_results.md` and `.csv`.

**Read these numbers carefully:** the test set is small, written by the same person who wrote the code, and includes deliberately hard cases.
It shows the guardrails *work on the cases we thought of*; it does not estimate real-world accuracy.
