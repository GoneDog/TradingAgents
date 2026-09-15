"""Minimal adapter compatibility checks; adversarial cases live in operator_safety."""

from decimal import Decimal

from tradingagents.operator.alpaca_oauth import AlpacaOAuthBroker
from tradingagents.operator.models import OrderIntent, utcnow


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.posts = []
        self.lookup_payload = None

    def get(self, url, timeout, **kwargs):
        if url.endswith("/v2/account"):
            return FakeResponse({"id": "test-account", "cash": "9000", "status": "ACTIVE",
                "trading_blocked": False, "account_blocked": False, "trade_suspended_by_user": False})
        if url.endswith("/v2/positions"):
            return FakeResponse([{"symbol": "AAPL", "market_value": "500", "qty": "2.5", "side": "long"}])
        if url.endswith("/v2/orders"):
            assert kwargs["params"]["status"] == "open"
            return FakeResponse([])
        if url.endswith("/v2/orders:by_client_order_id"):
            return FakeResponse(self.lookup_payload or {}, 200 if self.lookup_payload else 404)
        if url.endswith("/v2/clock"):
            return FakeResponse({"is_open": True})
        if "/v2/assets/" in url:
            return FakeResponse({"class": "us_equity", "tradable": True, "status": "active", "fractionable": True})
        raise AssertionError(url)

    def post(self, url, json, timeout, **kwargs):
        self.posts.append((url, json, timeout))
        return FakeResponse({"id": "broker-123", "client_order_id": json["client_order_id"], "status": "accepted"})


def test_uses_oauth_bearer_header_and_paper_endpoint():
    session = FakeSession()
    broker = AlpacaOAuthBroker("oauth-token", session=session)
    assert session.headers["Authorization"] == "Bearer oauth-token"
    assert "APCA-API-KEY-ID" not in session.headers
    assert broker.base_url == "https://paper-api.alpaca.markets"


def test_snapshot_reconciles_actual_positions():
    snapshot = AlpacaOAuthBroker("oauth-token", session=FakeSession()).snapshot()
    assert snapshot.cash == Decimal("9000")
    assert snapshot.gross_notional == Decimal("500")
    assert snapshot.symbol_quantities["AAPL"] == Decimal("2.5")
    assert snapshot.open_orders == 0


def test_submit_uses_client_order_id_and_limit_price():
    session = FakeSession()
    broker = AlpacaOAuthBroker("oauth-token", session=session)
    order = OrderIntent("AAPL", "buy", Decimal("1.25"), Decimal("200"), "ta-stable-id", Decimal("200"), utcnow())
    assert broker.submit(order).broker_order_id == "broker-123"
    assert session.posts[0][1]["client_order_id"] == "ta-stable-id"
    assert session.posts[0][1]["type"] == "limit"
    assert session.posts[0][1]["qty"] == "1.25"


def test_lookup_reconciles_by_client_order_id():
    session = FakeSession()
    session.lookup_payload = {"id": "broker-existing", "client_order_id": "ta-stable-id", "status": "filled"}
    receipt = AlpacaOAuthBroker("oauth-token", session=session).lookup("ta-stable-id")
    assert receipt.broker_order_id == "broker-existing" and receipt.status == "filled"


def test_lookup_returns_none_for_not_found():
    assert AlpacaOAuthBroker("oauth-token", session=FakeSession()).lookup("missing-id") is None
