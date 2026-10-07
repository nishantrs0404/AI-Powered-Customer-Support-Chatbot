function LoadingIndicator() {
    return (
        <div className="message bot">
            <div className="message-content">
                <div className="message-bubble typing">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    );
}

export default LoadingIndicator;