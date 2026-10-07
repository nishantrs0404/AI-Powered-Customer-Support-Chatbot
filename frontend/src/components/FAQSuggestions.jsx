function FAQSuggestions({ onSelect }) {
    const suggestions = [
        "Where is my order?",
        "How can I get a refund?",
        "How do I return a product?",
        "What payment methods do you accept?"
    ];

    return (
        <div className="faq-section">
            <p className="faq-title">Frequently asked questions</p>

            <div className="faq-suggestions">
                {suggestions.map((suggestion) => (
                    <button
                        key={suggestion}
                        className="faq-button"
                        onClick={() => onSelect(suggestion)}
                    >
                        {suggestion}
                    </button>
                ))}
            </div>
        </div>
    );
}

export default FAQSuggestions;