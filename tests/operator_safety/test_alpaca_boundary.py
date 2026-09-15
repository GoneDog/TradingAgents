import copy
from datetime import timedelta
from decimal import Decimal as D

import pytest

from tradingagents.operator.alpaca_oauth import AlpacaOAuthBroker
from tradingagents.operator.ledger import ReconciliationRequired
from tradingagents.operator.models import OrderIntent, utcnow


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return copy.deepcopy(self.data)


class Session:
    def __init__(self):
        self.headers = {"APCA-API-KEY-ID": "old", "APCA-API-SECRET-KEY": "old"}
        self.posts, self.gets = [], []
        self.account = {"id": "paper-account", "cash": "9000", "status": "ACTIVE",
            "trading_blocked": False, "account_blocked": False, "trade_suspended_by_user": False}
        self.positions = [{"symbol": "AAPL", "qty": "10", "qty_available": "6",
            "market_value": "1100", "side": "long"}]
        self.orders = [
            {"id": "buy", "client_order_id": "buy", "symbol": "MSFT", "side": "buy",
             "type": "limit", "qty": "9", "filled_qty": "3", "limit_price": "50", "status": "partially_filled"},
            {"id": "sell", "client_order_id": "sell", "symbol": "AAPL", "side": "sell",
             "type": "limit", "qty": "6", "filled_qty": "2", "limit_price": "100", "status": "partially_filled"},
        ]
        self.is_open = True
        self.asset = {"tradable": True, "status": "active", "class": "us_equity", "fractionable": True}
        self.quote = {"bp": 99, "ap": 101, "t": utcnow().isoformat()}
        self.lookup = None
        self.lookup_status = 404

    def get(self, url, timeout, **kwargs):
        assert kwargs.get("allow_redirects") is False
        self.gets.append((url, kwargs))
        if url.endswith("/v2/account"):
            return Response(self.account)
        if url.endswith("/v2/positions"):
            return Response(self.positions)
        if url.endswith("/v2/orders"):
            assert kwargs["params"] == {"status": "open", "limit": 500, "nested": "true"}
            return Response(self.orders)
        if url.endswith("/v2/orders:by_client_order_id"):
            return Response(self.lookup, self.lookup_status)
        if url.endswith("/v2/clock"):
            return Response({"is_open": self.is_open})
        if "/v2/assets/" in url:
            return Response(self.asset)
        if url.endswith("/quotes/latest"):
            assert kwargs["params"] == {"feed": "iex"}
            return Response({"quote": self.quote})
        raise AssertionError(url)

    def post(self, url, json, timeout, **kwargs):
        assert kwargs.get("allow_redirects") is False
        self.posts.append((url, json))
        return Response({"id": "submitted", "client_order_id": json["client_order_id"], "status": "accepted"})


def order():
    return OrderIntent("AAPL", "buy", D("1.25"), D("100"), "bounded-order", D("100.50"), utcnow())


def test_oauth_header_and_paper_only():
    session = Session()
    broker = AlpacaOAuthBroker("test-oauth-token", session=session)
    assert session.headers["Authorization"] == "Bearer test-oauth-token"
    assert "APCA-API-KEY-ID" not in session.headers
    assert "APCA-API-SECRET-KEY" not in session.headers
    assert broker.base_url == "https://paper-api.alpaca.markets"
    with pytest.raises(ValueError, match="live execution is disabled"):
        AlpacaOAuthBroker("test-oauth-token", paper=False, session=session)
    assert not session.posts


def test_snapshot_reserves_remaining_partial_fills_and_actual_shares():
    snapshot = AlpacaOAuthBroker("token", session=Session()).snapshot()
    assert snapshot.pending_buy_notionals == {"MSFT": D("300")}
    assert snapshot.pending_sell_quantities == {"AAPL": D("4")}
    assert snapshot.symbol_quantities == {"AAPL": D("10")}
    assert snapshot.available_to_sell("AAPL") == 6
    assert snapshot.gross_notional == 1100
    assert snapshot.open_orders == 2
    assert snapshot.account_id == "alpaca:paper:paper-account"


@pytest.mark.parametrize("change", ["market-buy", "complex", "missing-qty", "overfilled", "invalid-limit", "missing-id"])
def test_unsupported_pending_orders_fail_closed(change):
    session = Session()
    updates = {
        "market-buy": {"type": "market"}, "complex": {"order_class": "bracket"},
        "missing-qty": {"qty": None}, "overfilled": {"filled_qty": "10"},
        "invalid-limit": {"limit_price": "NaN"}, "missing-id": {"client_order_id": ""},
    }
    session.orders[0].update(updates[change])
    with pytest.raises(ReconciliationRequired):
        AlpacaOAuthBroker("token", session=session).snapshot()
    assert not session.posts


def test_truncated_order_response_fails_closed():
    session = Session()
    session.orders *= 250
    with pytest.raises(ReconciliationRequired, match="truncated"):
        AlpacaOAuthBroker("token", session=session).snapshot()


def test_short_positions_fail_closed():
    session = Session()
    session.positions[0]["side"] = "short"
    with pytest.raises(ReconciliationRequired, match="long equity"):
        AlpacaOAuthBroker("token", session=session).snapshot()


def test_changed_orders_during_snapshot_fail_closed():
    class ChangingSession(Session):
        def get(self, url, timeout, **kwargs):
            if url.endswith("/v2/orders"):
                self.orders[0]["filled_qty"] = str(int(self.orders[0]["filled_qty"]) + 1)
            return super().get(url, timeout, **kwargs)
    with pytest.raises(ReconciliationRequired, match="changed during"):
        AlpacaOAuthBroker("token", session=ChangingSession()).snapshot()


@pytest.mark.parametrize("field,value", [("status", "CLOSED"), ("trading_blocked", True), ("account_blocked", True), ("cash", "NaN")])
def test_invalid_account_state_fails_closed(field, value):
    session = Session()
    session.account[field] = value
    with pytest.raises(ReconciliationRequired):
        AlpacaOAuthBroker("token", session=session).snapshot()


def test_limit_order_payload_is_bounded_and_idempotency_key_preserved():
    session = Session()
    receipt = AlpacaOAuthBroker("token", session=session).submit(order())
    assert receipt.client_order_id == "bounded-order"
    payload = session.posts[0][1]
    assert payload["type"] == "limit"
    assert payload["limit_price"] == "100.50"
    assert payload["qty"] == "1.25"
    assert payload["time_in_force"] == "day"
    assert payload["extended_hours"] is False


def test_quote_uses_timestamped_iex_midpoint():
    session = Session()
    quote = AlpacaOAuthBroker("token", session=session).quote("aapl")
    assert quote.price == 100
    assert quote.as_of.tzinfo is not None
    assert any(url == "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest" for url, _ in session.gets)


def test_closed_market_does_not_submit_or_fetch_quote():
    session = Session()
    session.is_open = False
    broker = AlpacaOAuthBroker("token", session=session)
    with pytest.raises(ReconciliationRequired, match="session is closed"):
        broker.submit(order())
    with pytest.raises(ReconciliationRequired):
        broker.quote("AAPL")
    assert not session.posts


def test_nonfractionable_asset_does_not_submit():
    session = Session()
    session.asset["fractionable"] = False
    with pytest.raises(ValueError, match="fractional"):
        AlpacaOAuthBroker("token", session=session).submit(order())
    assert not session.posts


def test_stale_quote_does_not_submit():
    from dataclasses import replace
    session = Session()
    with pytest.raises(ValueError, match="stale"):
        AlpacaOAuthBroker("token", session=session).submit(replace(order(), price_as_of=utcnow() - timedelta(seconds=121)))
    assert not session.posts


def test_lookup_404_is_distinct_from_service_failure():
    session = Session()
    broker = AlpacaOAuthBroker("token", session=session)
    assert broker.lookup("missing") is None
    session.lookup_status = 503
    with pytest.raises(RuntimeError, match="503"):
        broker.lookup("unknown")


def test_nanosecond_quote_timestamp_is_normalized_for_python_310():
    session = Session()
    session.quote["t"] = "2026-09-15T14:30:00.123456789Z"
    quote = AlpacaOAuthBroker("token", session=session).quote("AAPL")
    assert quote.as_of.microsecond == 123456
