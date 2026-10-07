import MessageBubble from "./MessageBubble";

function MessageList({ messages }) {
    return (
        <div className="message-list">
            {messages.length === 0 ? (
                <div className="empty-chat">
                    <div className="empty-chat-icon">💬</div>

                    <h2>Start a conversation</h2>

                    <p>
                        Ask us anything about your order, payment, shipping,
                        returns, or products.
                    </p>
                </div>
            ) : (
                messages.map((message, index) => (
                    <MessageBubble
                        key={index}
                        sender={message.sender}
                        message={message.message}
                    />
                ))
            )}
        </div>
    );
}

export default MessageList;