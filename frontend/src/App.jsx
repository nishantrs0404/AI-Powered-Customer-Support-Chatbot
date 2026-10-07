import { useState } from "react";

import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import ChatInput from "./components/ChatInput";
import LoadingIndicator from "./components/LoadingIndicator";

import "./styles/global.css";

function App() {
  const [messages, setMessages] = useState([
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
  ]);

  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = (message) => {
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

  return (
    <div className="app">
      <div className="chat-container">
        <ChatHeader />

        <MessageList messages={messages} />

        {isLoading && <LoadingIndicator />}

        <ChatInput onSend={handleSendMessage} />
      </div>
    </div>
  );
}

export default App;