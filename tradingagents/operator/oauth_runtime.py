"""OAuth/keyless runtime configuration for unattended TradingAgents.

The unattended operator must not depend on metered provider API credentials.
LLM inference is reached through a local OpenAI-compatible OAuth bridge (for
example a Codex/ChatGPT OAuth proxy). Market-data vendors are restricted to
keyless sources.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class OAuthRuntimeConfig:
    """Configuration for subscription/OAuth-backed local inference."""

    backend_url: str = "http://127.0.0.1:9879/v1"
    deep_model: str = "gpt-5.5"
    quick_model: str = "gpt-5.5"

    def validate(self) -> None:
        parsed = urlparse(self.backend_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("OAuth inference backend must use http or https")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "Unattended OAuth inference must use a loopback bridge by default; "
                "remote relays require an explicit security review"
            )


def apply_oauth_only_policy(config: dict, runtime: OAuthRuntimeConfig | None = None) -> dict:
    """Return a TradingAgents config constrained to OAuth/keyless operation.

    ``openai_compatible`` points TradingAgents at a local bridge whose upstream
    authentication is OAuth.  The bridge may require a local-only client secret;
    that secret is transport authentication, not a metered model-provider key.
    """

    runtime = runtime or OAuthRuntimeConfig(
        backend_url=os.getenv("TRADINGAGENTS_OAUTH_BACKEND_URL", "http://127.0.0.1:9879/v1"),
        deep_model=os.getenv("TRADINGAGENTS_OAUTH_DEEP_MODEL", "gpt-5.5"),
        quick_model=os.getenv("TRADINGAGENTS_OAUTH_QUICK_MODEL", "gpt-5.5"),
    )
    runtime.validate()

    result = config.copy()
    result.update(
        {
            "llm_provider": "openai_compatible",
            "backend_url": runtime.backend_url,
            "deep_think_llm": runtime.deep_model,
            "quick_think_llm": runtime.quick_model,
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
                # FRED requires an API key in the current upstream implementation.
                # Disable it for the OAuth/keyless unattended profile.
                "macro_data": "",
                "prediction_markets": "polymarket",
            },
        }
    )
    return result


def reject_metered_provider_credentials(env: dict[str, str] | None = None) -> None:
    """Fail closed if metered provider credentials leak into this runtime."""

    env = env or os.environ
    forbidden = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_CN_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_CN_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "FRED_API_KEY",
    )
    present = sorted(name for name in forbidden if env.get(name))
    if present:
        raise RuntimeError(
            "OAuth-only runtime refuses metered provider credentials: " + ", ".join(present)
        )
