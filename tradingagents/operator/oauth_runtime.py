"""Local inference routing is NOT proof of OAuth upstream authentication or billing.

The bridge must be provisioned and verified separately. This module never logs
credentials, requests metered API keys, or falls back to a hosted provider.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class OAuthRuntimeConfig:
    backend_url: str = "http://127.0.0.1:9879/v1"
    deep_model: str = "gpt-5.5"
    quick_model: str = "gpt-5.5"

    def validate(self) -> None:
        parsed = urlparse(self.backend_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("OAuth inference backend must use http or https")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("OAuth inference must use a loopback bridge")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("bridge URL must not contain credentials, queries or fragments")
        if not self.deep_model.strip() or not self.quick_model.strip():
            raise ValueError("both model identifiers are required")


def apply_oauth_only_policy(config: dict, runtime: OAuthRuntimeConfig | None = None) -> dict:
    runtime = runtime or OAuthRuntimeConfig(
        backend_url=os.getenv("TRADINGAGENTS_OAUTH_BACKEND_URL", "http://127.0.0.1:9879/v1"),
        deep_model=os.getenv("TRADINGAGENTS_OAUTH_DEEP_MODEL", "gpt-5.5"),
        quick_model=os.getenv("TRADINGAGENTS_OAUTH_QUICK_MODEL", "gpt-5.5"))
    runtime.validate()
    result = config.copy()
    result.update({"llm_provider": "openai_compatible", "backend_url": runtime.backend_url,
        "deep_think_llm": runtime.deep_model, "quick_think_llm": runtime.quick_model,
        "tool_vendors": {},
        "data_vendors": {"core_stock_apis": "yfinance", "technical_indicators": "yfinance",
            "fundamental_data": "yfinance", "news_data": "yfinance", "macro_data": "",
            "prediction_markets": "polymarket"}})
    return result


FORBIDDEN_CREDENTIALS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY",
    "XAI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY", "ZHIPU_CN_API_KEY", "MINIMAX_API_KEY", "MINIMAX_CN_API_KEY",
    "ALPHA_VANTAGE_API_KEY", "FRED_API_KEY", "AZURE_OPENAI_API_KEY", "MISTRAL_API_KEY",
    "MOONSHOT_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
)


def reject_metered_provider_credentials(env: dict[str, str] | None = None) -> None:
    env = os.environ if env is None else env
    present = sorted(name for name in FORBIDDEN_CREDENTIALS if env.get(name))
    if present:
        raise RuntimeError("OAuth-only runtime refuses metered provider credentials: " + ", ".join(present))
