"""Unattended trading operator primitives.

The operator layer is deliberately separate from the LLM research graph. Agents
may propose trades; deterministic policy code decides whether a proposal is
allowed to reach an execution adapter.
"""

from .alpaca_oauth import AlpacaOAuthBroker
from .broker import BrokerAdapter, DryRunBroker
from .ledger import Ledger
from .models import Decision, OrderIntent, RiskLimits
from .oauth_runtime import OAuthRuntimeConfig, apply_oauth_only_policy, reject_metered_provider_credentials
from .planner import DecisionPlanner, PositionTargets
from .risk import RiskGate, RiskRejection

__all__ = [
    "AlpacaOAuthBroker",
    "BrokerAdapter",
    "Decision",
    "DecisionPlanner",
    "DryRunBroker",
    "Ledger",
    "OAuthRuntimeConfig",
    "OrderIntent",
    "PositionTargets",
    "RiskGate",
    "RiskLimits",
    "RiskRejection",
    "apply_oauth_only_policy",
    "reject_metered_provider_credentials",
]
