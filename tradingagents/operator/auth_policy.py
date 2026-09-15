from __future__ import annotations

from .rails import RailCapabilities


class RailAuthViolation(RuntimeError):
    pass


class OAuthOnlyRailPolicy:
    """Production authentication policy.

    Unattended execution is permitted only on OAuth bearer rails. User-signed
    wallets may still be connected for balances/treasury operations, but are not
    treated as unattended execution rails. Signed API-key or delegated app-secret
    rails remain disabled unless the user explicitly changes this policy.
    """

    OAUTH_MODES = frozenset({
        "oauth2_bearer_pay_scope",
        "oauth2_bearer_trading_scope",
    })

    def validate(self, rail: RailCapabilities, *, unattended: bool) -> None:
        if unattended and rail.auth_mode not in self.OAUTH_MODES:
            raise RailAuthViolation(
                f"{rail.name} is not permitted for unattended execution under OAuth-only policy"
            )
        if unattended and rail.per_transaction_user_signature:
            raise RailAuthViolation(f"{rail.name} requires a user signature")
