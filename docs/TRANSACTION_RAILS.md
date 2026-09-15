# Transaction rails

The unattended operator treats financial execution as capability-scoped rails. Secrets are never committed.

## Current target topology

1. **Phantom treasury** — user-controlled source/treasury wallet. Connecting and signing remain user-authorized. The unattended service never receives the seed phrase or private key.
2. **Delegated agent wallet (Privy signer)** — small hot wallet for offline/agentic Solana or EVM execution. The user grants a signer once; server-side policies constrain destinations/actions. Default local policy caps this role at $250 until explicitly changed.
3. **Revolut Business OAuth** — fiat balance, internal transfer and FX execution using bearer access with READ/PAY scopes. This is distinct from Plaid/Finances read access.
4. **Alpaca OAuth** — equities/crypto brokerage execution behind the same deterministic mandate layer.

## Explicitly excluded from the OAuth-only default

- Revolut X authenticated trading currently uses an API key plus Ed25519 request signatures, so it is excluded from the default OAuth-only execution path.
- A normal Phantom connected wallet requires a user signature for wallet transactions; it is therefore a treasury/approval rail rather than an unattended signer.

## Secret boundary

Runtime credentials belong in a host secret manager or environment injected at service start. Never commit:

- Revolut access/refresh tokens or client assertion signing keys
- delegated-wallet authorization/signing keys
- Phantom seed phrases/private keys
- broker OAuth tokens

## Promotion to real funds

No rail receives live funds merely because it connects successfully. The sequence is:

`connect -> read/reconcile -> sandbox/paper -> bounded transaction test -> live-capped`

The deterministic mandate remains authoritative over every transaction regardless of model output.
