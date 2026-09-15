from __future__ import annotations

from decimal import Decimal
import requests


class RevolutBusinessOAuthRail:
    """Revolut Business execution client using OAuth bearer access.

    This is intentionally separate from Plaid/Finances read access. The access
    token must carry the required Revolut Business READ/PAY scopes. Credentials
    are supplied at runtime and never stored in the repository.
    """

    BASE_URL = "https://b2b.revolut.com/api/1.0"

    def __init__(self, access_token: str, *, timeout: float = 15.0, session=None):
        if not access_token:
            raise ValueError("Revolut Business OAuth access token is required")
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
        response = self.session.get(self.BASE_URL + path, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict):
        response = self.session.post(
            self.BASE_URL + path, json=payload, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def accounts(self) -> list[dict]:
        return self._get("/accounts")

    def balance(self, currency: str) -> Decimal:
        currency = currency.upper()
        total = Decimal("0")
        for account in self.accounts():
            if str(account.get("currency", "")).upper() == currency:
                total += Decimal(str(account.get("balance", "0")))
        return total

    def internal_transfer(
        self,
        *,
        request_id: str,
        source_account_id: str,
        target_account_id: str,
        amount: Decimal,
        currency: str,
        reference: str = "agent transfer",
    ) -> dict:
        return self._post(
            "/transfer",
            {
                "request_id": request_id,
                "source_account_id": source_account_id,
                "target_account_id": target_account_id,
                "amount": float(amount),
                "currency": currency.upper(),
                "reference": reference,
            },
        )

    def exchange(
        self,
        *,
        request_id: str,
        source_account_id: str,
        source_currency: str,
        target_account_id: str,
        target_currency: str,
        amount: Decimal,
        reference: str = "agent exchange",
    ) -> dict:
        return self._post(
            "/exchange",
            {
                "from": {
                    "account_id": source_account_id,
                    "currency": source_currency.upper(),
                    "amount": float(amount),
                },
                "to": {
                    "account_id": target_account_id,
                    "currency": target_currency.upper(),
                },
                "reference": reference,
                "request_id": request_id,
            },
        )
