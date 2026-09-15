from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal

import requests

from .broker import AccountSnapshot, OrderReceipt
from .ledger import ReconciliationRequired
from .models import OrderIntent, PriceQuote, canonical_symbol, finite, utcnow


def _decimal(value, name: str) -> Decimal:
    try:
        return finite(Decimal(str(value)), name)
    except Exception as exc:
        raise ReconciliationRequired(f"missing or invalid broker field: {name}") from exc


class AlpacaOAuthBroker:
    """OAuth, US-equity, regular-session LIMIT orders. Live mode stays disabled.

    Supply an already-authorized bearer token securely; this is not an OAuth
    authorization flow. Quotes explicitly use IEX, not an auto-selected paid feed.
    """

    PAPER_URL = "https://paper-api.alpaca.markets"
    DATA_URL = "https://data.alpaca.markets"

    def __init__(self, access_token: str, *, paper: bool = True,
                 timeout: float = 15.0, session: requests.Session | None = None):
        if not access_token:
            raise ValueError("Alpaca OAuth access token is required")
        if paper is not True:
            raise ValueError("live execution is disabled pending end-to-end validation")
        self.base_url = self.PAPER_URL
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.pop("APCA-API-KEY-ID", None)
        self.session.headers.pop("APCA-API-SECRET-KEY", None)
        self.session.headers.update({"Authorization": f"Bearer {access_token}",
            "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": "TradingAgents-Unattended/0.2"})

    def _get(self, path: str, *, data: bool = False, **kwargs):
        response = self.session.get((self.DATA_URL if data else self.base_url) + path,
                                    timeout=self.timeout, allow_redirects=False, **kwargs)
        response.raise_for_status()
        if response.status_code != 200:
            raise ReconciliationRequired("unexpected broker HTTP status")
        return response.json()

    @staticmethod
    def _receipt(order: dict) -> OrderReceipt:
        if any(not isinstance(order.get(key), str) or not order[key] for key in ("client_order_id", "id", "status")):
            raise ReconciliationRequired("broker returned an incomplete receipt")
        return OrderReceipt(order["client_order_id"], order["id"], order["status"])

    def _open_orders(self):
        orders = self._get("/v2/orders", params={"status": "open", "limit": 500, "nested": "true"})
        if not isinstance(orders, list) or len(orders) >= 500:
            raise ReconciliationRequired("open-order response may be truncated")
        return orders

    def snapshot(self) -> AccountSnapshot:
        before = self._open_orders()
        account = self._get("/v2/account")
        positions = self._get("/v2/positions")
        orders = self._open_orders()
        def normalize(rows):
            return sorted(json.dumps(row, sort_keys=True) for row in rows)
        if normalize(before) != normalize(orders):
            raise ReconciliationRequired("open orders changed during account snapshot")
        if account.get("status") != "ACTIVE" or any(account.get(flag, True) is not False for flag in ("trading_blocked", "account_blocked", "trade_suspended_by_user")):
            raise ReconciliationRequired("account is not confirmed active and unrestricted")
        if not isinstance(account.get("id"), str) or not account["id"]:
            raise ReconciliationRequired("broker account identity is missing")
        notionals, quantities, available = {}, {}, {}
        for position in positions:
            symbol = canonical_symbol(position["symbol"])
            if position.get("side") != "long" or symbol in quantities:
                raise ReconciliationRequired("only unique long equity positions are supported")
            notionals[symbol] = _decimal(position["market_value"], "market_value")
            quantities[symbol] = _decimal(position["qty"], "qty")
            available[symbol] = _decimal(position.get("qty_available", position["qty"]), "qty_available")
        buys, sells, ids = {}, {}, set()
        for order in orders:
            if order.get("order_class") not in (None, "", "simple") or order.get("legs"):
                raise ReconciliationRequired("complex open orders require separate reconciliation")
            symbol = canonical_symbol(order["symbol"])
            client_id = order.get("client_order_id")
            if not client_id or client_id in ids:
                raise ReconciliationRequired("open-order identity is missing or duplicated")
            ids.add(client_id)
            qty = _decimal(order.get("qty"), "order qty")
            filled = _decimal(order.get("filled_qty"), "filled_qty")
            if filled > qty:
                raise ReconciliationRequired("filled quantity exceeds order quantity")
            remaining = qty - filled
            if order["side"] == "buy":
                if order.get("type") != "limit":
                    raise ReconciliationRequired("unbounded pending buy order")
                limit = _decimal(order.get("limit_price"), "limit_price")
                if limit <= 0:
                    raise ReconciliationRequired("pending buy has no positive price bound")
                buys[symbol] = buys.get(symbol, Decimal("0")) + remaining * limit
            elif order["side"] == "sell":
                sells[symbol] = sells.get(symbol, Decimal("0")) + remaining
            else:
                raise ReconciliationRequired("unknown open-order side")
        snapshot = AccountSnapshot(cash=_decimal(account.get("cash"), "cash"),
            gross_notional=sum(notionals.values(), Decimal("0")), open_orders=len(orders),
            symbol_notionals=notionals, symbol_quantities=quantities,
            pending_buy_notionals=buys, pending_sell_quantities=sells,
            available_quantities=available, open_order_ids=frozenset(ids),
            account_id=f"alpaca:paper:{account['id']}")
        snapshot.validate()
        return snapshot

    def lookup(self, client_order_id: str) -> OrderReceipt | None:
        response = self.session.get(self.base_url + "/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id}, timeout=self.timeout, allow_redirects=False)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if response.status_code != 200:
            raise ReconciliationRequired("unexpected broker lookup status")
        return self._receipt(response.json())

    def _market_open(self) -> None:
        if self._get("/v2/clock").get("is_open") is not True:
            raise ReconciliationRequired("regular trading session is closed")

    def quote(self, symbol: str) -> PriceQuote:
        self._market_open()
        symbol = canonical_symbol(symbol)
        quote = self._get(f"/v2/stocks/{symbol}/quotes/latest", data=True, params={"feed": "iex"})["quote"]
        bid, ask = _decimal(quote.get("bp"), "bid"), _decimal(quote.get("ap"), "ask")
        if bid <= 0 or ask < bid:
            raise ReconciliationRequired("invalid or crossed quote")
        # Python 3.10 accepts microseconds; Alpaca can send nanoseconds.
        text = re.sub(r"(\.\d{6})\d+", r"\1", quote["t"].replace("Z", "+00:00"))
        stamp = datetime.fromisoformat(text)
        return PriceQuote((bid + ask) / 2, stamp)

    def submit(self, intent: OrderIntent) -> OrderReceipt:
        if intent.symbol != canonical_symbol(intent.symbol) or intent.side not in {"buy", "sell"}:
            raise ValueError("invalid order symbol or side")
        finite(intent.quantity, "quantity", positive=True)
        finite(intent.limit_price, "limit_price", positive=True)
        if intent.price_as_of is None or intent.price_as_of.tzinfo is None:
            raise ValueError("timestamped execution quote is required")
        age = (utcnow() - intent.price_as_of).total_seconds()
        if age < -5 or age > 120:
            raise ValueError("execution quote is stale or in the future")
        tick = Decimal("0.01") if intent.limit_price >= 1 else Decimal("0.0001")
        if intent.limit_price.quantize(tick) != intent.limit_price:
            raise ValueError("limit price has unsupported precision")
        self._market_open()
        asset = self._get(f"/v2/assets/{intent.symbol}")
        if asset.get("tradable") is not True or asset.get("status") != "active" or asset.get("class") != "us_equity":
            raise ValueError("asset is not a tradable US equity")
        if intent.quantity != intent.quantity.to_integral_value() and asset.get("fractionable") is not True:
            raise ValueError("asset does not support fractional quantities")
        payload = {"symbol": intent.symbol, "qty": str(intent.quantity), "side": intent.side,
            "type": "limit", "limit_price": str(intent.limit_price),
            "time_in_force": "day", "extended_hours": False, "client_order_id": intent.client_order_id}
        response = self.session.post(self.base_url + "/v2/orders", json=payload,
                                     timeout=self.timeout, allow_redirects=False)
        response.raise_for_status()
        if response.status_code not in (200, 201):
            raise ReconciliationRequired("unexpected broker submission status")
        return self._receipt(response.json())
