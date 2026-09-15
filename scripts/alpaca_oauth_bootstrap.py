#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import json
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from tradingagents.operator.alpaca_oauth_bootstrap import (
    AlpacaOAuthApp,
    build_authorization_url,
    exchange_code,
    write_token_file,
)


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        type(self).code = params.get("code", [None])[0]
        type(self).state = params.get("state", [None])[0]
        type(self).error = params.get("error", [None])[0]
        body = b"Alpaca authorization received. You may close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=("paper", "live"), default="paper")
    parser.add_argument(
        "--token-file",
        default="~/.config/tradingagents/alpaca-oauth.json",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = AlpacaOAuthApp.from_env()
    callback = urllib.parse.urlparse(app.redirect_uri)
    if callback.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("bootstrap callback must be loopback")
    if not callback.port:
        raise SystemExit("redirect URI must include a loopback port")

    auth_url, expected_state = build_authorization_url(app, environment=args.env)
    server = http.server.HTTPServer((callback.hostname, callback.port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(auth_url)
    if not args.no_browser:
        webbrowser.open(auth_url)
    thread.join()
    server.server_close()

    if CallbackHandler.error:
        raise SystemExit(f"authorization failed: {CallbackHandler.error}")
    if not CallbackHandler.code or CallbackHandler.state != expected_state:
        raise SystemExit("authorization callback failed state validation")

    payload = exchange_code(app, code=CallbackHandler.code)
    target = write_token_file(payload, Path(args.token_file))
    print(json.dumps({"status": "authorized", "environment": args.env, "token_file": str(target)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
