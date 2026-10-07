function FAQSuggestions({ onSelect }) {
    const suggestions = [
        {
            label: "📦 Order status",
            question: "Where is my order?"
        },
        {
            label: "💰 Refund",
            question: "How can I get a refund?"
        },
        {
            label: "↩️ Return",
            question: "How do I return a product?"
        },
        {
            label: "💳 Payment",
            question: "What payment methods do you accept?"
        }
    ];

    return (
        <div className="faq-section">
            <p className="faq-title">
                Frequently asked questions
            </p>

            <div className="faq-suggestions">
                {suggestions.map((suggestion) => (
                    <button
                        key={suggestion.question}
                        className="faq-button"
                        onClick={() => onSelect(suggestion.question)}
                    >
                        {suggestion.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

export default FAQSuggestions;