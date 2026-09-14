from __future__ import annotations

from decimal import Decimal

import requests

from .broker import AccountSnapshot, OrderReceipt
from .models import OrderIntent


class AlpacaOAuthBroker:
    """Trading API adapter authenticated only with an Alpaca OAuth bearer token.

    No APCA API-key headers are supported here. The OAuth token is obtained by a
    separate one-time authorization flow and supplied to this process securely.
    """

    LIVE_URL = "https://api.alpaca.markets"
    PAPER_URL = "https://paper-api.alpaca.markets"

    def __init__(
        self,
        access_token: str,
        *,
        paper: bool = True,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ):
        if not access_token:
            raise ValueError("Alpaca OAuth access token is required")
        self.base_url = self.PAPER_URL if paper else self.LIVE_URL
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "TradingAgents-Unattended/0.1",
            }
        )

    def _get(self, path: str, **kwargs):
        response = self.session.get(
            self.base_url + path,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _receipt(order: dict, fallback_client_order_id: str = "") -> OrderReceipt:
        return OrderReceipt(
            client_order_id=str(order.get("client_order_id", fallback_client_order_id)),
            broker_order_id=str(order["id"]),
            status=str(order.get("status", "accepted")),
        )

    def snapshot(self) -> AccountSnapshot:
        account = self._get("/v2/account")
        positions = self._get("/v2/positions")
        orders = self._get("/v2/orders", params={"status": "open", "limit": 500})

        symbol_notionals: dict[str, Decimal] = {}
        gross = Decimal("0")
        for position in positions:
            market_value = abs(Decimal(str(position.get("market_value", "0"))))
            if str(position.get("side", "long")).lower() == "short":
                signed_value = -market_value
            else:
                signed_value = market_value
            symbol_notionals[str(position["symbol"])] = signed_value
            gross += market_value

        return AccountSnapshot(
            cash=Decimal(str(account.get("cash", "0"))),
            gross_notional=gross,
            open_orders=len(orders),
            symbol_notionals=symbol_notionals,
        )

    def lookup(self, client_order_id: str) -> OrderReceipt | None:
        response = self.session.get(
            self.base_url + "/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._receipt(response.json(), client_order_id)

    def submit(self, intent: OrderIntent) -> OrderReceipt:
        payload = {
            "symbol": intent.symbol,
            "qty": str(intent.quantity),
            "side": intent.side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": intent.client_order_id,
        }
        response = self.session.post(
            self.base_url + "/v2/orders",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._receipt(response.json(), intent.client_order_id)
