
def test_create_message_saves_user_message(client):
    conversation_response = client.post(
        "/api/v1/conversations"
    )

    assert conversation_response.status_code == 201

    session_id = conversation_response.json()["session_id"]

    message_response = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": "Where is my order?"},
    )

    assert message_response.status_code == 201

    saved_message = message_response.json()

    assert saved_message["id"] > 0
    assert saved_message["conversation_id"] == (
        conversation_response.json()["id"]
    )
    assert saved_message["role"] == "user"
    assert saved_message["content"] == "Where is my order?"
    assert saved_message["created_at"]


def test_create_message_rejects_unknown_conversation(client):
    response = client.post(
        "/api/v1/conversations/nonexistent-session/messages",
        json={"message": "Where is my order?"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_create_message_rejects_empty_message(client):
    conversation_response = client.post(
        "/api/v1/conversations"
    )

    session_id = conversation_response.json()["session_id"]

    response = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": "   "},
    )

    assert response.status_code == 422


def test_get_conversation_messages_returns_chronological_history(client):
    conversation_response = client.post(
        "/api/v1/conversations"
    )

    assert conversation_response.status_code == 201

    session_id = conversation_response.json()["session_id"]

    first_message = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": "Hello"},
    )

    second_message = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": "Where is my order?"},
    )

    assert first_message.status_code == 201
    assert second_message.status_code == 201

    history_response = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    )

    assert history_response.status_code == 200

    history = history_response.json()

    assert len(history) == 2
    assert history[0]["content"] == "Hello"
    assert history[1]["content"] == "Where is my order?"
    assert history[0]["id"] < history[1]["id"]


def test_get_conversation_messages_returns_empty_list(client):
    conversation_response = client.post(
        "/api/v1/conversations"
    )

    session_id = conversation_response.json()["session_id"]

    history_response = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    )

    assert history_response.status_code == 200
    assert history_response.json() == []


def test_get_conversation_messages_rejects_unknown_session(client):
    response = client.get(
        "/api/v1/conversations/nonexistent-session/messages"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
