"""Real operator code, fake broker/LLM, and no network or provider credentials."""

import pytest
import requests

from tradingagents.operator.oauth_runtime import FORBIDDEN_CREDENTIALS


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    # Override the parent's placeholder keys: the operator rejects those too.
    for name in FORBIDDEN_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _isolate_config():
    # These tests inject the graph and never load the global LLM/dataflow config.
    yield


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden in safety tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
