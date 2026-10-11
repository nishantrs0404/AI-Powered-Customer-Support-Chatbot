from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Conversation, Message


def test_conversation_and_messages_are_persisted(tmp_path):
    database_file = tmp_path / "test_chatbot.db"

    test_engine = create_engine(
        f"sqlite:///{database_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    try:
        Base.metadata.create_all(bind=test_engine)

        with Session(test_engine) as session:
            conversation = Conversation(session_id="test-session-001")
            conversation.messages.append(
                Message(role="user", content="Where is my order?")
            )
            conversation.messages.append(
                Message(
                    role="assistant",
                    content="I can help you check your order.",
                )
            )

            session.add(conversation)
            session.commit()

        with Session(test_engine) as session:
            saved_conversation = session.scalar(
                select(Conversation).where(
                    Conversation.session_id == "test-session-001"
                )
            )

            assert saved_conversation is not None
            assert len(saved_conversation.messages) == 2
            assert saved_conversation.messages[0].role == "user"
            assert (
                saved_conversation.messages[0].content
                == "Where is my order?"
            )
            assert saved_conversation.messages[1].role == "assistant"
    finally:
        test_engine.dispose()
