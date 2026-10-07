function MessageBubble({ sender, message }) {
    return (
        <div className={`message ${sender}`}>
            <div className="message-bubble">
                {message}
            </div>
        </div>
    );
}

export default MessageBubble;