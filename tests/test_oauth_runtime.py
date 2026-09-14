import pytest

from tradingagents.operator.oauth_runtime import (
    OAuthRuntimeConfig,
    apply_oauth_only_policy,
    reject_metered_provider_credentials,
)


def test_oauth_policy_uses_local_openai_compatible_bridge():
    config = {"llm_provider": "openai", "data_vendors": {"macro_data": "fred"}}
    result = apply_oauth_only_policy(
        config,
        OAuthRuntimeConfig(
            backend_url="http://127.0.0.1:9879/v1",
            deep_model="deep",
            quick_model="quick",
        ),
    )

    assert result["llm_provider"] == "openai_compatible"
    assert result["backend_url"] == "http://127.0.0.1:9879/v1"
    assert result["deep_think_llm"] == "deep"
    assert result["quick_think_llm"] == "quick"
    assert result["data_vendors"]["core_stock_apis"] == "yfinance"
    assert result["data_vendors"]["macro_data"] == ""


def test_oauth_policy_rejects_remote_bridge_by_default():
    with pytest.raises(ValueError, match="loopback"):
        OAuthRuntimeConfig(backend_url="https://example.com/v1").validate()


def test_metered_provider_credentials_fail_closed():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        reject_metered_provider_credentials({"OPENAI_API_KEY": "secret"})


def test_local_transport_secret_is_not_rejected():
    reject_metered_provider_credentials({"LOCAL_OAUTH_BRIDGE_KEY": "local-only"})
