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
    id: 1,
    sender: "bot",
    message: "Hello! How can I help you today?",
    timestamp: new Date()
  },
  {
    id: 2,
    sender: "user",
    message: "Where is my order?",
    timestamp: new Date()
  },
  {
    id: 3,
    sender: "bot",
    message: "Sure! Please provide your order ID.",
    timestamp: new Date()
  }
];

function generateMockResponse(message) {
  const text = message.toLowerCase();

  if (
    text.includes("order") ||
    text.includes("track") ||
    text.includes("shipping")
  ) {
    return "I can help you check your order status. Please provide your order ID.";
  }

  if (
    text.includes("refund") ||
    text.includes("money back")
  ) {
    return "I can help with your refund request. Please provide your order ID so we can check the refund status.";
  }

  if (
    text.includes("return") ||
    text.includes("exchange")
  ) {
    return "Sure! I can help you with a return or exchange. Please provide your order ID.";
  }

  if (
    text.includes("payment") ||
    text.includes("pay")
  ) {
    return "We support multiple payment methods. Please let me know if you are having a problem with a specific payment.";
  }

  if (
    text.includes("hello") ||
    text.includes("hi") ||
    text.includes("hey")
  ) {
    return "Hello! I'm happy to help. What can I assist you with today?";
  }

  return "Thanks for contacting us. Could you provide a little more information so I can help you better?";
}

function App() {
  const [messages, setMessages] = useState(initialMessages);

  const [isLoading, setIsLoading] = useState(false);

  const [error, setError] = useState(null);

  const handleSendMessage = (message) => {
    if (isLoading) {
      return;
    }

    setError(null);

    const userMessage = {
      id: Date.now(),
      sender: "user",
      message: message,
      timestamp: new Date()
    };

    setMessages((previousMessages) => [
      ...previousMessages,
      userMessage
    ]);

    setIsLoading(true);

    setTimeout(() => {
      const botMessage = {
        id: Date.now() + 1,
        sender: "bot",
        message: generateMockResponse(message),
        timestamp: new Date()
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