from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import PromotionState, StrategyCandidate, ValidationResult


class StrategyRegistry:
    """Durable provenance ledger for candidate, validated, paper and live strategies."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    strategy_id TEXT PRIMARY KEY,
                    candidate_json TEXT NOT NULL,
                    state TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS validations (
                    strategy_id TEXT NOT NULL,
                    test_fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, test_fingerprint)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def register(self, candidate: StrategyCandidate) -> None:
        payload = json.dumps(candidate.__dict__, sort_keys=True, default=list)
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO strategies VALUES (?, ?, ?)",
                (candidate.strategy_id, payload, PromotionState.CANDIDATE.value),
            )

    def record_validation(self, result: ValidationResult) -> None:
        payload = json.dumps(result.__dict__, sort_keys=True, default=list)
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO validations VALUES (?, ?, ?)",
                (result.strategy_id, result.test_fingerprint, payload),
            )

    def state(self, strategy_id: str) -> PromotionState:
        with self._connect() as con:
            row = con.execute(
                "SELECT state FROM strategies WHERE strategy_id = ?", (strategy_id,)
            ).fetchone()
        if row is None:
            raise KeyError(strategy_id)
        return PromotionState(row[0])

    def transition(
        self,
        strategy_id: str,
        to_state: PromotionState,
        *,
        actor: str,
        reason: str,
    ) -> None:
        current = self.state(strategy_id)
        if current == to_state:
            return
        allowed = {
            PromotionState.CANDIDATE: {PromotionState.REJECTED, PromotionState.PAPER},
            PromotionState.PAPER: {PromotionState.LIVE_CAPPED, PromotionState.REJECTED, PromotionState.RETIRED},
            PromotionState.LIVE_CAPPED: {PromotionState.RETIRED},
            PromotionState.REJECTED: set(),
            PromotionState.RETIRED: set(),
        }
        if to_state not in allowed[current]:
            raise ValueError(f"invalid strategy transition: {current.value} -> {to_state.value}")
        with self._connect() as con:
            con.execute(
                "UPDATE strategies SET state = ? WHERE strategy_id = ?",
                (to_state.value, strategy_id),
            )
            con.execute(
                "INSERT INTO transitions (strategy_id, from_state, to_state, actor, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (strategy_id, current.value, to_state.value, actor, reason),
            )
