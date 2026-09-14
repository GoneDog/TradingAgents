from decimal import Decimal

from tradingagents.operator.alpaca_oauth import AlpacaOAuthBroker
from tradingagents.operator.models import OrderIntent


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
            return FakeResponse({"cash": "9000"})
        if url.endswith("/v2/positions"):
            return FakeResponse(
                [
                    {"symbol": "AAPL", "market_value": "500", "side": "long"},
                    {"symbol": "TSLA", "market_value": "200", "side": "short"},
                ]
            )
        if url.endswith("/v2/orders"):
            assert kwargs["params"]["status"] == "open"
            return FakeResponse([{"id": "open-1"}])
        if url.endswith("/v2/orders:by_client_order_id"):
            if self.lookup_payload is None:
                return FakeResponse({}, status_code=404)
            return FakeResponse(self.lookup_payload)
        raise AssertionError(url)

    def post(self, url, json, timeout):
        self.posts.append((url, json, timeout))
        return FakeResponse(
            {
                "id": "broker-123",
                "client_order_id": json["client_order_id"],
                "status": "accepted",
            }
        )


def test_uses_oauth_bearer_header_and_paper_endpoint():
    session = FakeSession()
    broker = AlpacaOAuthBroker("oauth-token", session=session)
    assert session.headers["Authorization"] == "Bearer oauth-token"
    assert "APCA-API-KEY-ID" not in session.headers
    assert broker.base_url == "https://paper-api.alpaca.markets"


def test_snapshot_reconciles_positions_and_open_orders():
    broker = AlpacaOAuthBroker("oauth-token", session=FakeSession())
    snapshot = broker.snapshot()
    assert snapshot.cash == Decimal("9000")
    assert snapshot.gross_notional == Decimal("700")
    assert snapshot.open_orders == 1
    assert snapshot.symbol_notionals["AAPL"] == Decimal("500")
    assert snapshot.symbol_notionals["TSLA"] == Decimal("-200")


def test_submit_uses_client_order_id_for_broker_idempotency():
    session = FakeSession()
    broker = AlpacaOAuthBroker("oauth-token", session=session)
    intent = OrderIntent(
        symbol="AAPL",
        side="buy",
        quantity=Decimal("1.25"),
        reference_price=Decimal("200"),
        client_order_id="ta-stable-id",
    )
    receipt = broker.submit(intent)
    assert receipt.broker_order_id == "broker-123"
    assert session.posts[0][1]["client_order_id"] == "ta-stable-id"
    assert session.posts[0][1]["qty"] == "1.25"


def test_lookup_reconciles_by_client_order_id():
    session = FakeSession()
    session.lookup_payload = {
        "id": "broker-existing",
        "client_order_id": "ta-stable-id",
        "status": "filled",
    }
    broker = AlpacaOAuthBroker("oauth-token", session=session)
    receipt = broker.lookup("ta-stable-id")
    assert receipt is not None
    assert receipt.broker_order_id == "broker-existing"
    assert receipt.status == "filled"


def test_lookup_returns_none_for_definitive_not_found():
    broker = AlpacaOAuthBroker("oauth-token", session=FakeSession())
    assert broker.lookup("missing-id") is None
