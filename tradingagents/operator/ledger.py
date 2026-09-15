from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .broker import OrderReceipt
from .models import Decision, OrderIntent

TERMINAL = frozenset({"filled", "canceled", "expired", "rejected"})


class ReconciliationRequired(RuntimeError):
    """Do not submit until broker/account state has been established."""


class IntentConflict(RuntimeError):
    pass


def _encode(intent: OrderIntent) -> str:
    return json.dumps({
        "symbol": intent.symbol, "side": intent.side, "quantity": str(intent.quantity),
        "reference_price": str(intent.reference_price), "client_order_id": intent.client_order_id,
        "limit_price": str(intent.limit_price) if intent.limit_price is not None else None,
        "price_as_of": intent.price_as_of.isoformat() if intent.price_as_of else None,
    }, sort_keys=True)


def _decode(payload: str) -> OrderIntent:
    data = json.loads(payload)
    for name in ("quantity", "reference_price", "limit_price"):
        if data[name] is not None:
            data[name] = Decimal(data[name])
    if data["price_as_of"]:
        data["price_as_of"] = datetime.fromisoformat(data["price_as_of"])
    return OrderIntent(**data)


class Ledger:
    """One durable ledger per account, shared by every worker on one local host."""

    def __init__(self, path: str | Path):
        if str(path) == ":memory:":
            raise ValueError("a persistent, local ledger path is required")
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.exclusive(), self._connect() as con:
            columns = {row[1] for row in con.execute("PRAGMA table_info(orders)")}
            if columns and "intent_json" not in columns:
                if con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
                    raise ReconciliationRequired("legacy ledger contains orders; reconcile and archive it before migration")
                con.execute("DROP TABLE orders")
            con.execute("CREATE TABLE IF NOT EXISTS orders (client_order_id TEXT PRIMARY KEY, intent_json TEXT NOT NULL, broker_order_id TEXT, status TEXT NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS decisions (decision_key TEXT PRIMARY KEY, symbol TEXT NOT NULL, decision TEXT NOT NULL, client_order_id TEXT)")
            con.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def exclusive(self):
        # Separate lock DB permits durable state commits before network I/O.
        # SQLite releases this process lock even when a worker crashes.
        if getattr(self._local, "locked", False):
            yield
            return
        con = sqlite3.connect(self.path + ".lock", timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE")
            self._local.locked = True
            yield
        finally:
            self._local.locked = False
            con.rollback()
            con.close()

    def bind_account(self, account_id: str) -> None:
        if not account_id:
            raise ValueError("account identity is required")
        with self._connect() as con:
            con.execute("INSERT OR IGNORE INTO metadata VALUES ('account_id', ?)", (account_id,))
            bound = con.execute("SELECT value FROM metadata WHERE key='account_id'").fetchone()[0]
            if bound != account_id:
                raise ReconciliationRequired("ledger belongs to a different account or environment")

    def get_order(self, client_order_id: str):
        with self._connect() as con:
            return con.execute("SELECT * FROM orders WHERE client_order_id=?", (client_order_id,)).fetchone()

    def has_order(self, client_order_id: str) -> bool:
        return self.get_order(client_order_id) is not None

    def get_intent(self, client_order_id: str) -> OrderIntent | None:
        row = self.get_order(client_order_id)
        return _decode(row["intent_json"]) if row else None

    def active_orders(self):
        with self._connect() as con:
            return [row for row in con.execute("SELECT * FROM orders") if row["status"] not in TERMINAL]

    @staticmethod
    def _insert_intent(con, intent: OrderIntent) -> None:
        payload = _encode(intent)
        con.execute("INSERT OR IGNORE INTO orders (client_order_id,intent_json,status) VALUES (?,?,'pending')", (intent.client_order_id, payload))
        existing = con.execute("SELECT intent_json FROM orders WHERE client_order_id=?", (intent.client_order_id,)).fetchone()[0]
        if existing != payload:
            raise IntentConflict("client order ID already belongs to a different immutable intent")

    def record_pending(self, intent: OrderIntent) -> None:
        with self._connect() as con:
            self._insert_intent(con, intent)

    def set_status(self, client_order_id: str, status: str) -> None:
        with self._connect() as con:
            if con.execute("UPDATE orders SET status=? WHERE client_order_id=?", (status, client_order_id)).rowcount != 1:
                raise ReconciliationRequired("cannot update an unknown order")

    def record_receipt(self, receipt: OrderReceipt) -> None:
        if not receipt.broker_order_id or not receipt.status:
            raise ReconciliationRequired("broker returned an incomplete receipt")
        with self._connect() as con:
            if con.execute("UPDATE orders SET broker_order_id=?,status=? WHERE client_order_id=?", (receipt.broker_order_id, receipt.status, receipt.client_order_id)).rowcount != 1:
                raise ReconciliationRequired("broker receipt has an unknown client order ID")

    def get_decision(self, decision_key: str):
        with self._connect() as con:
            return con.execute("SELECT * FROM decisions WHERE decision_key=?", (decision_key,)).fetchone()

    def record_decision(self, key: str, symbol: str, decision: Decision, intent: OrderIntent | None) -> None:
        with self._connect() as con:
            if intent is not None:
                self._insert_intent(con, intent)
            con.execute("INSERT INTO decisions VALUES (?,?,?,?)", (key, symbol, decision.value, intent.client_order_id if intent else None))
