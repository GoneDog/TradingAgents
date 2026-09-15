# Alpaca Connect bootstrap

This project uses Alpaca Connect OAuth for Trading API execution. It does not use Trading API key/secret authentication.

## One-time Alpaca Connect app registration

Create an OAuth application from Alpaca Dashboard -> Alpaca Connect -> My Developed Apps.

Use these application values unless Alpaca requires a public HTTPS callback during review:

- App name: `TradingAgents Unattended Operator`
- Purpose: personal automated research/paper trading service with deterministic risk limits
- Requested Trading API scope: `trading`
- Development callback: `http://127.0.0.1:8765/oauth/callback`
- Initial environment: `paper`

Do not commit the issued Client ID, Client Secret, authorization code, or bearer token.

## Local authorization

Export the OAuth app credentials into the service environment:

```bash
export ALPACA_OAUTH_CLIENT_ID='...'
export ALPACA_OAUTH_CLIENT_SECRET='...'
export ALPACA_OAUTH_REDIRECT_URI='http://127.0.0.1:8765/oauth/callback'
```

Then run:

```bash
python scripts/alpaca_oauth_bootstrap.py --env paper
```

The script:

1. Generates a cryptographically random OAuth `state` value.
2. Opens Alpaca's authorization page with `env=paper` and `scope=trading`.
3. Captures the loopback callback.
4. Rejects a callback whose `state` does not match.
5. Exchanges the temporary authorization code server-side.
6. Writes the token response to `~/.config/tradingagents/alpaca-oauth.json` with mode `0600`.

The token file is runtime material and must remain outside the repository.

## Activation

Receiving an OAuth token does **not** activate live trading. The operator remains in paper mode until an explicit `live_capped` mandate passes `tradingagents.operator.activation`.

A live mandate requires all of:

- maximum total capital,
- maximum per-order notional,
- maximum daily loss,
- explicit market allowlist,
- withdrawals disabled.

The service must never infer live-capital authorization from account connection alone.
