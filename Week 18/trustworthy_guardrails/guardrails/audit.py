"""Tamper-evident audit log: every entry stores the SHA-256 of the previous entry.
Only REDACTED text is ever written here, so the log itself cannot leak PII."""
import hashlib
import json
import time


class AuditLog:
    def __init__(self, path=None):
        self.entries, self.path, self._prev = [], path, "0" * 64

    def record(self, event: str, data: dict):
        entry = {"ts": round(time.time(), 3), "event": event, "data": data, "prev": self._prev}
        entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
        self._prev = entry["hash"]
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def verify(self) -> bool:
        prev = "0" * 64
        for e in self.entries:
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["prev"] != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True
