"""单场花费。按 token 估算，到顶后不再打云端，改说现成的短句。"""
from __future__ import annotations

from .config import feature_on


class SessionBudget:
    def __init__(self) -> None:
        self.tokens = 0
        self.spent = 0.0
        self.calls = 0
        self.failures = 0

    def reset(self) -> None:
        self.tokens = 0
        self.spent = 0.0
        self.calls = 0
        self.failures = 0

    def add(self, cfg: dict, tokens: int) -> None:
        amount = max(0, int(tokens or 0))
        self.tokens += amount
        self.calls += 1
        rate = float((cfg.get("budget") or {}).get("cny_per_1k") or 0)
        self.spent += amount / 1000 * rate

    def fail(self) -> None:
        self.failures += 1

    def tripped(self, cfg: dict) -> bool:
        if not feature_on(cfg, "budget"):
            return False
        cap = float((cfg.get("budget") or {}).get("cap_cny") or 0)
        if cap <= 0:
            return False
        return self.spent >= cap

    def public(self, cfg: dict) -> dict:
        cap = float((cfg.get("budget") or {}).get("cap_cny") or 0)
        return {
            "spent_cny": round(self.spent, 4),
            "cap_cny": cap,
            "tokens": self.tokens,
            "calls": self.calls,
            "failures": self.failures,
            "tripped": self.tripped(cfg),
            "estimated": True,
        }
