import { useState } from "react";

function ChatInput({ onSend }) {
    const [message, setMessage] = useState("");

    const handleSend = () => {
        const trimmedMessage = message.trim();

        if (!trimmedMessage) {
            return;
        }

        onSend(trimmedMessage);
        setMessage("");
    };

    const handleKeyDown = (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="chat-input-area">
            <div className="chat-input">
                <input
                    type="text"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type your message..."
                    maxLength={2000}
                />

                <button
                    onClick={handleSend}
                    disabled={!message.trim()}
                >
                    Send
                </button>
            </div>

            <p className="input-hint">
                Press Enter to send
            </p>
        </div>
    );
}

export default ChatInput;