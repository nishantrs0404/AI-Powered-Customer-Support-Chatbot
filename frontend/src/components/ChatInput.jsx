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
        if (event.key === "Enter") {
            handleSend();
        }
    };

    return (
        <div className="chat-input">
            <input
                type="text"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
            />

            <button onClick={handleSend}>
                Send
            </button>
        </div>
    );
}

export default ChatInput;