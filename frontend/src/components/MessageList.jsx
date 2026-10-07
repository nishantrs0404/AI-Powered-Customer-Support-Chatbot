import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

function MessageList({ messages }) {
    const messagesEndRef = useRef(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({
            behavior: "smooth"
        });
    }, [messages]);

    return (
        <div className="message-list">
            {messages.length === 0 ? (
                <div className="empty-chat">
                    <div className="empty-chat-icon">💬</div>

                    <h2>Start a conversation</h2>

                    <p>
                        Ask us anything about your order, payment,
                        shipping, returns, or products.
                    </p>
                </div>
            ) : (
                messages.map((message, index) => (
                    <MessageBubble
                        key={message.id || index}
                        sender={message.sender}
                        message={message.message}
                        timestamp={message.timestamp}
                    />
                ))
            )}

            <div ref={messagesEndRef}></div>
        </div>
    );
}

export default MessageList;