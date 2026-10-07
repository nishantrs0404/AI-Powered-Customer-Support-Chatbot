function MessageBubble({ sender, message }) {
    const time = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    });

    return (
        <div className={`message ${sender}`}>
            <div className="message-content">
                <div className="message-bubble">
                    {message}
                </div>

                <span className="message-time">
                    {time}
                </span>
            </div>
        </div>
    );
}

export default MessageBubble;