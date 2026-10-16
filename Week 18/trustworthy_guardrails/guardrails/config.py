"""Central configuration: thresholds, canned messages, public contact allow-list."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # --- input guardrails ---
    max_input_chars: int = 2000
    injection_block_threshold: float = 0.70   # score >= this  -> block
    injection_flag_threshold: float = 0.40    # score >= this  -> flag (allow + harden prompt)
    # --- output guardrails ---
    answer_max_chars: int = 600
    groundedness_min_coverage: float = 0.60   # share of a claim's content words found in a reference doc
    number_context_min_overlap: float = 0.50  # a number must sit in a reference sentence about the same thing
    max_regenerations: int = 1
    # --- system prompt leak detection ---
    canary: str = "CANARY-7f3a91"
    # Public bank contacts are NOT private data, so they are allowed in answers.
    public_contacts: tuple = ("01-5550000", "support@everestbank.com.np")


CATEGORIES = ("account", "card", "loan", "transfer", "support", "general")

MESSAGES = {
    "refuse_injection": "I can't help with that request. I can answer questions about accounts, cards, loans and transfers.",
    "refuse_topic": "I'm sorry, I can't help with that request.",
    "refuse_too_long": "Your message is too long. Please shorten it and try again.",
    "crisis": ("I'm really sorry you're going through this. You don't have to handle it alone. "
               "Please reach out to someone you trust or a local emergency or mental-health helpline right now. "
               "If you are in immediate danger, contact your local emergency services."),
    "fallback": ("I couldn't produce a verified answer to that. Please contact our helpline "
                 "01-5550000 (Sunday to Friday, 9:00 AM to 5:00 PM) for help."),
    "disclaimer_legal": "Note: this is general information, not legal advice. Please consult a qualified lawyer.",
    "disclaimer_investment": "Note: this is not financial advice. Please consult a licensed financial adviser.",
}
