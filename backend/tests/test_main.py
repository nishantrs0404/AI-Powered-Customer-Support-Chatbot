
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "customer-support-chatbot",
    }


def test_valid_message_is_accepted():
    response = client.post(
        "/api/v1/validate-message",
        json={"message": "I need help with my order"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "character_count": 25,
    }


def test_empty_message_is_rejected():
    response = client.post(
        "/api/v1/validate-message",
        json={"message": "   "},
    )

    assert response.status_code == 422


def test_message_over_2000_characters_is_rejected():
    response = client.post(
        "/api/v1/validate-message",
        json={"message": "a" * 2001},
    )

    assert response.status_code == 422


def test_missing_message_is_rejected():
    response = client.post(
        "/api/v1/validate-message",
        json={},
    )

    assert response.status_code == 422
