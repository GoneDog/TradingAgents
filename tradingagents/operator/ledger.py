from __future__ import annotations

import sqlite3
from pathlib import Path

from .broker import OrderReceipt
from .models import OrderIntent


class Ledger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    reference_price TEXT NOT NULL,
                    broker_order_id TEXT,
                    status TEXT NOT NULL
                )
                """
            )

    def has_order(self, client_order_id: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM orders WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        return row is not None

    def record_pending(self, intent: OrderIntent) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO orders
                (client_order_id, symbol, side, quantity, reference_price, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (
                    intent.client_order_id,
                    intent.symbol,
                    intent.side,
                    str(intent.quantity),
                    str(intent.reference_price),
                ),
            )

    def record_receipt(self, receipt: OrderReceipt) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE orders
                SET broker_order_id = ?, status = ?
                WHERE client_order_id = ?
                """,
                (receipt.broker_order_id, receipt.status, receipt.client_order_id),
            )
