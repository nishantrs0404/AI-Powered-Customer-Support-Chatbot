import { useState, useEffect, useCallback } from "react";

import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import ChatInput from "./components/ChatInput";
import LoadingIndicator from "./components/LoadingIndicator";
import FAQSuggestions from "./components/FAQSuggestions";
import ErrorMessage from "./components/ErrorMessage";

import { createConversation, sendMessage } from "./services/api";

import "./styles/global.css";

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);

  // Create a conversation session when the app mounts.
  const initConversation = useCallback(async () => {
    try {
      const conversation = await createConversation();
      setSessionId(conversation.session_id);
    } catch {
      // Backend may be unreachable — the user can still type and
      // the error will surface when they send a message.
      setSessionId(null);
    }
  }, []);

  useEffect(() => {
    initConversation();
  }, [initConversation]);

  const handleSendMessage = async (message) => {
    if (isLoading) {
      return;
    }

    setError(null);

    const userMessage = {
      id: Date.now(),
      sender: "user",
      message: message,
      timestamp: new Date(),
    };

    setMessages((previousMessages) => [...previousMessages, userMessage]);
    setIsLoading(true);

    try {
      // If we don't have a session yet (backend was down on mount), try now.
      let currentSessionId = sessionId;
      if (!currentSessionId) {
        const conversation = await createConversation();
        currentSessionId = conversation.session_id;
        setSessionId(currentSessionId);
      }

      const reply = await sendMessage(currentSessionId, message);

      const botMessage = {
        id: reply.id || Date.now() + 1,
        sender: "bot",
        message: reply.content,
        timestamp: reply.created_at ? new Date(reply.created_at) : new Date(),
      };

      setMessages((previousMessages) => [...previousMessages, botMessage]);
    } catch (err) {
      setError(
        err.message || "Could not reach the server. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestionSelect = (suggestion) => {
    handleSendMessage(suggestion);
  };

  const handleClearChat = async () => {
    setMessages([]);
    setError(null);
    setIsLoading(false);

    // Start a fresh conversation so history is clean.
    await initConversation();
  };

  const handleRetry = () => {
    setError(null);

    // Retry the last user message if one exists.
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.sender === "user");

    if (lastUserMessage) {
      // Remove the last user message so handleSendMessage can re-add it.
      setMessages((prev) => prev.filter((m) => m.id !== lastUserMessage.id));
      handleSendMessage(lastUserMessage.message);
    }
  };

  return (
    <div className="app">
      <div className="chat-container">

        <ChatHeader onClearChat={handleClearChat} />

        <MessageList messages={messages} />

        {messages.length === 0 && (
          <FAQSuggestions
            onSelect={handleSuggestionSelect}
          />
        )}

        {error && (
          <ErrorMessage
            message={error}
            onRetry={handleRetry}
          />
        )}

        {isLoading && <LoadingIndicator />}

        <ChatInput
          onSend={handleSendMessage}
          disabled={isLoading}
        />

      </div>
    </div>
  );
}

export default App;
