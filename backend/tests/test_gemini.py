
from fastapi.testclient import TestClient

from app.main import app


def test_ai_reply_returns_generated_response(monkeypatch):
    def fake_generate_reply(message: str) -> str:
        assert message == "What are your support hours?"
        return "Our support team is available 24/7."

    monkeypatch.setattr(
        "app.main.generate_reply",
        fake_generate_reply,
    )

    with TestClient(app) as client:
        response = client.post(
            "/ai/reply",
            json={"message": "What are your support hours?"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Our support team is available 24/7."
    }


def test_ai_reply_handles_gemini_failure(monkeypatch):
    def fake_generate_reply(message: str) -> str:
        raise RuntimeError("Gemini is temporarily unavailable.")

    monkeypatch.setattr(
        "app.main.generate_reply",
        fake_generate_reply,
    )

    with TestClient(app) as client:
        response = client.post(
            "/ai/reply",
            json={"message": "Hello"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Gemini could not generate a response. Please try again."
    )


def test_ai_reply_rejects_empty_message():
    with TestClient(app) as client:
        response = client.post(
            "/ai/reply",
            json={"message": ""},
        )

    assert response.status_code == 422
