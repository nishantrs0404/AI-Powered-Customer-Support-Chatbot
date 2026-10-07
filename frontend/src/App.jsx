import { useState } from "react";

import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import ChatInput from "./components/ChatInput";
import LoadingIndicator from "./components/LoadingIndicator";
import FAQSuggestions from "./components/FAQSuggestions";
import ErrorMessage from "./components/ErrorMessage";

import "./styles/global.css";

const initialMessages = [
  {
    sender: "bot",
    message: "Hello! How can I help you today?"
  },
  {
    sender: "user",
    message: "Where is my order?"
  },
  {
    sender: "bot",
    message: "Sure! Please provide your order ID."
  }
];

function App() {
  const [messages, setMessages] = useState(initialMessages);

  const [isLoading, setIsLoading] = useState(false);

  const [error, setError] = useState(null);

  const handleSendMessage = (message) => {
    setError(null);

    const userMessage = {
      sender: "user",
      message: message
    };

    setMessages((previousMessages) => [
      ...previousMessages,
      userMessage
    ]);

    setIsLoading(true);

    setTimeout(() => {
      const botMessage = {
        sender: "bot",
        message:
          "Thanks for your message! Our support system is processing your request."
      };

      setMessages((previousMessages) => [
        ...previousMessages,
        botMessage
      ]);

      setIsLoading(false);
    }, 1000);
  };

  const handleSuggestionSelect = (suggestion) => {
    handleSendMessage(suggestion);
  };

  const handleClearChat = () => {
    setMessages([]);
    setError(null);
    setIsLoading(false);
  };

  const handleRetry = () => {
    setError(null);
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