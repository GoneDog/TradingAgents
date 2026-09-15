import os
import stat
import urllib.parse

from tradingagents.operator.alpaca_oauth_bootstrap import (
    AlpacaOAuthApp,
    build_authorization_url,
    write_token_file,
)


def test_authorization_url_is_paper_trading_and_stateful():
    app = AlpacaOAuthApp("client", "secret", "http://127.0.0.1:8765/oauth/callback")
    url, state = build_authorization_url(app, environment="paper", state="fixed-state")
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    assert params["client_id"] == ["client"]
    assert params["scope"] == ["trading"]
    assert params["env"] == ["paper"]
    assert params["state"] == ["fixed-state"]
    assert state == "fixed-state"


def test_token_file_is_owner_only(tmp_path):
    target = write_token_file({"access_token": "secret"}, tmp_path / "token.json")
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600
