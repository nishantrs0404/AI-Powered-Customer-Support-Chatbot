function ChatHeader() {
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

            <div className="online-status">
                <span className="online-dot"></span>
                <span>Online</span>
            </div>
        </header>
    );
}

export default ChatHeader;