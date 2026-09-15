from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256


class PromotionState(str, Enum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    PAPER = "paper"
    LIVE_CAPPED = "live_capped"
    RETIRED = "retired"


@dataclass(frozen=True)
class StrategyCandidate:
    name: str
    hypothesis: str
    strategy_spec: dict
    data_version: str
    generator: str
    created_at: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def strategy_id(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "hypothesis": self.hypothesis,
                "strategy_spec": self.strategy_spec,
                "data_version": self.data_version,
                "generator": self.generator,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode()).hexdigest()[:20]


@dataclass(frozen=True)
class ValidationResult:
    strategy_id: str
    validator: str
    passed: bool
    reasons: tuple[str, ...]
    metrics: dict[str, float]
    test_fingerprint: str
