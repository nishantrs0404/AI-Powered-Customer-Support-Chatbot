import { useState } from "react";

function ChatInput({ onSend, disabled = false }) {
    const [message, setMessage] = useState("");

    const handleSend = () => {
        const trimmedMessage = message.trim();

        if (!trimmedMessage || disabled) {
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
                    placeholder={
                        disabled
                            ? "Waiting for response..."
                            : "Type your message..."
                    }
                    maxLength={2000}
                    disabled={disabled}
                />

                <button
                    onClick={handleSend}
                    disabled={!message.trim() || disabled}
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