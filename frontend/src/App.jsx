import { useState, useEffect, useCallback, useRef } from "react";

import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import ChatInput from "./components/ChatInput";
import LoadingIndicator from "./components/LoadingIndicator";
import FAQSuggestions from "./components/FAQSuggestions";
import ErrorMessage from "./components/ErrorMessage";

import {
  createConversation,
  sendMessage,
  getConversationMessages,
} from "./services/api";

import "./styles/global.css";

const SESSION_STORAGE_KEY = "chat_session_id";

function getStoredSessionId() {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredSessionId(id) {
  try {
    if (id) {
      localStorage.setItem(SESSION_STORAGE_KEY, id);
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch {
    // Graceful fallback for restricted environments
  }
}

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(() => getStoredSessionId());

  // Ref to synchronously prevent rapid duplicate sends
  const isSendingRef = useRef(false);

  // Initialize or restore conversation session on mount
  const initConversation = useCallback(async () => {
    setError(null);
    const storedSessionId = getStoredSessionId();

    if (storedSessionId) {
      try {
        const history = await getConversationMessages(storedSessionId);
        setSessionId(storedSessionId);

        if (Array.isArray(history) && history.length > 0) {
          const restoredMessages = history.map((msg) => ({
            id: msg.id,
            sender: msg.role === "user" ? "user" : "bot",
            message: msg.content,
            timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
          }));
          setMessages(restoredMessages);
        } else {
          setMessages([]);
        }
        return;
      } catch (err) {
        // If session no longer exists in backend database (404), clear stale key
        if (err.status === 404) {
          setStoredSessionId(null);
        } else {
          // Network failure: keep storedSessionId in state so it can be resumed
          setSessionId(storedSessionId);
          return;
        }
      }
    }

    // No existing session or stale session removed: create a fresh conversation
    try {
      const conversation = await createConversation();
      setSessionId(conversation.session_id);
      setStoredSessionId(conversation.session_id);
      setMessages([]);
    } catch {
      // Backend may be offline; session will be created on first message send
      setSessionId(null);
    }
  }, []);

  useEffect(() => {
    initConversation();
  }, [initConversation]);

  const handleSendMessage = async (message) => {
    const trimmedMessage = typeof message === "string" ? message.trim() : "";

    // Reject empty messages or duplicate sends while a request is in progress
    if (!trimmedMessage || isLoading || isSendingRef.current) {
      return;
    }

    isSendingRef.current = true;
    setIsLoading(true);
    setError(null);

    const tempUserMessage = {
      id: Date.now(),
      sender: "user",
      message: trimmedMessage,
      timestamp: new Date(),
    };

    setMessages((previousMessages) => [...previousMessages, tempUserMessage]);

    try {
      // Ensure we have an active session ID
      let currentSessionId = sessionId || getStoredSessionId();
      if (!currentSessionId) {
        const conversation = await createConversation();
        currentSessionId = conversation.session_id;
        setSessionId(currentSessionId);
        setStoredSessionId(currentSessionId);
      }

      const reply = await sendMessage(currentSessionId, trimmedMessage);

      // Ensure storage is in sync with the active session
      if (getStoredSessionId() !== currentSessionId) {
        setStoredSessionId(currentSessionId);
      }

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
      isSendingRef.current = false;
    }
  };

  const handleSuggestionSelect = (suggestion) => {
    handleSendMessage(suggestion);
  };

  const handleClearChat = async () => {
    setMessages([]);
    setError(null);
    setIsLoading(false);
    isSendingRef.current = false;

    // Remove stored session ID so the new chat starts with clean context
    setStoredSessionId(null);
    setSessionId(null);

    try {
      const conversation = await createConversation();
      setSessionId(conversation.session_id);
      setStoredSessionId(conversation.session_id);
    } catch {
      setSessionId(null);
    }
  };

  const handleRetry = () => {
    setError(null);

    // Find the last user message to retry
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.sender === "user");

    if (lastUserMessage) {
      // Remove the last unreplied user message and re-submit
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
