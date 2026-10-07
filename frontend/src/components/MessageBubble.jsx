function MessageBubble({ sender, message, timestamp }) {
    const formattedTime = timestamp
        ? new Date(timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        })
        : "";

    return (
        <div className={`message ${sender}`}>
            <div className="message-content">
                <div className="message-bubble">
                    {message}
                </div>

                {formattedTime && (
                    <span className="message-time">
                        {formattedTime}
                    </span>
                )}
            </div>
        </div>
    );
}

export default MessageBubble;