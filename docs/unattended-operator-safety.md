# Unattended operator: repaired boundary, not a live deployment

This revision repairs PR #1's local safety boundary. It does not claim a working
OAuth inference bridge, a deployed scheduler, broker authorization, profitability,
or live-trading readiness. `AlpacaOAuthBroker(paper=False)` is deliberately rejected.
No live execution switch or metered model-provider fallback is provided.

## Execution contract

Use one dedicated paper account and one persistent local SQLite ledger shared by
all workers. Do not use separate ledgers, a network filesystem, or another host
for concurrent writers to the same account. A separate SQLite lock database
serializes research, planning, reconciliation, validation and submission; its lock
is released on process exit. Ledger state commits remain durable before POST.
Account and environment identity are bound to the ledger. A nonempty legacy
ledger must be reconciled and archived deliberately, never silently migrated or
deleted to bypass a halt.

Snapshots include actual shares, available shares, remaining pending buys at
their limit prices, remaining pending sells, and broker client-order IDs. Pending
sells never free buying capacity before fills. Partial fills reserve only their
remaining quantity. Unknown/unbounded buy orders, complex orders, truncated
results, short positions and changing order snapshots halt execution.
A long-only reduction can proceed when price appreciation puts exposure over a
cap, but it must respect the available-share and individual-order-size limits.
Caps bound new order commitments, not future mark-to-market value or all fees.

Execution pricing no longer uses Yahoo daily closes. The adapter requests a
timestamped IEX quote using the existing OAuth bearer token. It does not select
a paid feed on failure. Orders are regular-session US-equity DAY limit orders;
fractional support and asset tradability are checked. A quote older than 120
seconds or meaningfully in the future is rejected. Limit prices bound execution
price, not completion: orders may remain unfilled and require reconciliation.
RiskLimits can set a tighter age policy; the adapter never relaxes its 120-second
maximum. The default allowed price deviation is 50 basis points, a configurable
software ceiling rather than a claim of trading suitability.

## Durable decisions and recovery

`run_once(symbol, decision_version="v1")` records at most one immutable decision
for the current New York date, canonical symbol and version. This includes HOLD,
REVIEW and decisions that create no order. A retry reloads the stored decision
and order without calling the model or obtaining a replacement price. Intentionally
new decisions require a new version; do not generate a new version just to bypass
an unresolved submission or an unfilled order.

Order IDs exclude price, rating, target and quantity. Their payload is immutable.
A `pending` record means no submission attempt has begun. Immediately before
submission it becomes `submitting`; exceptions leave it `unknown`. Following an
attempt, even a broker 404 is not permission to resubmit. The operator must find
the existing order through broker reconciliation or halt. Pending/ambiguous work
blocks unrelated submissions. Filled, canceled, expired or rejected outcomes
remain recorded rather than being silently resubmitted under a new price.

A crash after the submitting marker but before the network call can therefore
require deliberate reconciliation. This trades automatic recovery in an ambiguous
case for duplicate prevention. HTTP/authorization failures are not converted into
unbounded retries or automatic authentication workarounds. External/manual orders
and broker endpoint consistency still require a real integration test; two REST
snapshots are not an atomic brokerage transaction.

## OAuth constraint

`oauth_runtime.py` pins inference to a loopback compatible endpoint, removes
per-tool vendor overrides and rejects known metered-provider credentials. The
upstream client reads `OPENAI_COMPATIBLE_API_KEY` for a local bridge's transport
secret; that must not be a metered provider key. A loopback address or a variable
name does not establish the bridge's actual upstream authentication or billing.
Verify the existing authorized subscription-backed bridge and its model/tool-call
support separately. Do not copy tokens into GitHub, chat, fixtures or logs.

## Verification and next gate

The isolated tests run the real operator modules with fake brokerage/LLM transports.
`tests/operator_safety/conftest.py` blocks requests networking and removes model
provider credentials. Run:

```sh
python -m pytest --confcutdir=tests/operator_safety tests/operator_safety -q
```

The dedicated workflow needs no secrets and runs Python 3.10-3.13. Existing full
repository CI remains in place. Local isolated tests do not substitute for the
complete upstream suite or an authenticated integration test.

Before deployment: validate the authorized OAuth inference bridge end to end;
verify OAuth broker scopes, quotes, fills and cancellation/reconciliation in the
paper environment; add a supervised service, kill switch and exception alerts;
then conduct a separate live-readiness review. Do not merge merely to imply those
steps happened. Nothing in this patch performs account linking or submits orders.

Protocol references:
- https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api
- https://docs.alpaca.markets/us/docs/working-with-orders
