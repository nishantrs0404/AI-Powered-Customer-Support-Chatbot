function ErrorMessage({ message, onRetry }) {
    return (
        <div className="error-message">
            <div>
                <strong>Something went wrong.</strong>

                <p>
                    {message || "Please try again."}
                </p>
            </div>

            {onRetry && (
                <button onClick={onRetry}>
                    Retry
                </button>
            )}
        </div>
    );
}

export default ErrorMessage;