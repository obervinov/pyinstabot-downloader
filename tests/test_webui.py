"""Tests for basic WebUI functionality using FastAPI TestClient."""
import hashlib
import hmac
import os
import time

import pytest
from fastapi.testclient import TestClient

from src.modules.webui import WebUI


@pytest.fixture(scope="session", name="webui_setup")
def fixture_webui_setup(database_class, vault_instance):
    """Create a WebUI instance and TestClient for integration-style tests."""
    bot_token = os.getenv("TG_TOKEN")
    if not bot_token:
        pytest.skip("TG_TOKEN environment variable is required for WebUI tests")

    webui = WebUI(
        database=database_class,
        vault=vault_instance,
        bot_token=bot_token,
        bot_username=os.getenv("TG_USERNAME", "test_bot"),
        session_secret="test-secret",
        host="0.0.0.0",
        port=8080,
        templates_dir="src/templates",
        version="test"
    )
    client = TestClient(webui.app)
    return {"webui": webui, "client": client, "bot_token": bot_token}


def _make_auth_payload(bot_token: str, user_id: str = "test_user_1") -> dict:
    """Construct a valid Telegram Login Widget payload for testing."""
    auth_data = {
        "id": user_id,
        "first_name": "Test",
        "username": "testuser",
        "photo_url": "https://example.com/avatar.jpg",
        "auth_date": str(int(time.time())),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(auth_data.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    auth_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    auth_data["hash"] = auth_hash
    return auth_data


def _login(client: TestClient, bot_token: str):
    """Authenticate the TestClient session via Telegram callback."""
    payload = _make_auth_payload(bot_token)
    response = client.get("/auth/telegram", params=payload, allow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers.get("location", "").endswith("/dashboard")


@pytest.mark.order(17)
def test_webui_instance(webui_setup):
    webui = webui_setup["webui"]
    assert webui.host == "0.0.0.0"
    assert webui.port == 8080
    assert webui.bot_token is not None
    assert webui.session_secret is not None
    assert webui.bot_username is not None


@pytest.mark.order(18)
def test_webui_login_page(webui_setup):
    client = webui_setup["client"]
    response = client.get("/")
    assert response.status_code == 200
    assert "data-telegram-login" in response.text


@pytest.mark.order(19)
def test_webui_auth_and_dashboard(webui_setup):
    client = webui_setup["client"]
    bot_token = webui_setup["bot_token"]

    _login(client, bot_token)
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    # Basic sanity checks on rendered dashboard
    assert "queue" in dashboard.text.lower()


@pytest.mark.order(20)
def test_webui_queue_requires_auth(webui_setup):
    client = TestClient(webui_setup["webui"].app)  # fresh client without session
    response = client.get("/api/queue")
    assert response.status_code == 401


@pytest.mark.order(21)
def test_webui_queue_data_for_user(webui_setup):
    client = webui_setup["client"]
    bot_token = webui_setup["bot_token"]

    _login(client, bot_token)
    response = client.get("/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["messages"]) == 1
    assert data["messages"][0]["post_id"] == "test_post_1"


@pytest.mark.order(22)
def test_webui_submit_invalid_url(webui_setup):
    client = webui_setup["client"]
    bot_token = webui_setup["bot_token"]

    _login(client, bot_token)
    response = client.post("/api/submit", data={"url": "not_a_valid_link"})
    assert response.status_code == 400
    assert response.json().get("detail") == "Invalid Instagram URL"
