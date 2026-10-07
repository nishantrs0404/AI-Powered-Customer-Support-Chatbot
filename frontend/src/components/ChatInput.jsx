import { useState } from "react";

const MAX_MESSAGE_LENGTH = 2000;

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
                    maxLength={MAX_MESSAGE_LENGTH}
                    disabled={disabled}
                />

                <button
                    onClick={handleSend}
                    disabled={!message.trim() || disabled}
                >
                    Send
                </button>
            </div>

            <div className="input-footer">
                <p className="input-hint">
                    Press Enter to send
                </p>

                <span className="character-count">
                    {message.length}/{MAX_MESSAGE_LENGTH}
                </span>
            </div>
        </div>
    );
}

export default ChatInput;