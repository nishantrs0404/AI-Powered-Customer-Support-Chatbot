function ChatHeader({ onClearChat }) {
    return (
        <header className="chat-header">
            <div className="header-left">
                <div className="bot-avatar">
                    🤖
                </div>

                <div>
                    <h1>AI Customer Support</h1>
                    <p>We're here to help you</p>
                </div>
            </div>

            <div className="header-actions">
                <div className="online-status">
                    <span className="online-dot"></span>
                    <span>Online</span>
                </div>

                <button
                    className="clear-button"
                    onClick={onClearChat}
                    title="Clear conversation"
                >
                    Clear
                </button>
            </div>
        </header>
    );
}

export default ChatHeader;