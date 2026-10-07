import MessageBubble from "./MessageBubble";

function MessageList({ messages }) {
    return (
        <div className="message-list">
            {messages.map((message, index) => (
                <MessageBubble
                    key={index}
                    sender={message.sender}
                    message={message.message}
                />
            ))}
        </div>
    );
}

export default MessageList;