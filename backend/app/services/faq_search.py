import re
from typing import Any

from app.services.faq_service import load_faqs


STOP_WORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were",
    "do", "does", "did", "can", "could", "would", "should",
    "how", "what", "when", "where", "why", "who", "which",
    "i", "me", "my", "we", "our", "you", "your", "it",
    "to", "for", "of", "in", "on", "at", "and", "or",
    "please", "tell", "about", "get", "have", "has", "had",
    # Function words & conversational particles
    "be", "been", "being",
    "not", "no", "nor",
    "that", "this", "these", "those",
    "there", "then", "here",
    "if", "but", "by", "from", "with", "as",
    "just", "very", "also", "so", "than", "too",
    # Contraction fragments produced by regex word splitting
    "t", "s", "m", "d", "ll", "ve", "re",
    "don", "doesn", "didn", "hasn", "haven", "hadn",
    "won", "wouldn", "couldn", "shouldn",
    "isn", "aren", "wasn", "weren",
}


def normalize_text(text: str) -> str:
    """Convert text to lowercase words separated by single spaces."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def tokenize(text: str) -> set[str]:
    """Return meaningful words for matching."""
    return {
        word
        for word in normalize_text(text).split()
        if word not in STOP_WORDS
    }


def calculate_score(query: str, faq: dict[str, Any]) -> float:
    """Calculate a relevance score between 0.0 and 1.0."""
    normalized_query = normalize_text(query)

    if not normalized_query:
        return 0.0

    question = normalize_text(faq["question"])
    keywords = [normalize_text(word) for word in faq["keywords"]]

    # Give the highest score to an exact question or keyword match.
    if normalized_query == question or normalized_query in keywords:
        return 1.0

    # Reward a complete keyword phrase appearing as whole words in the query.
    if any(
        keyword and bool(re.search(rf"\b{re.escape(keyword)}\b", normalized_query))
        for keyword in keywords
    ):
        return 0.9

    query_words = tokenize(query)
    faq_words = tokenize(
        faq["question"] + " " + " ".join(faq["keywords"])
    )

    if not query_words or not faq_words:
        return 0.0

    common_words = query_words & faq_words

    if not common_words:
        return 0.0

    coverage = len(common_words) / len(query_words)
    jaccard = len(common_words) / len(query_words | faq_words)

    score = (0.75 * coverage) + (0.25 * jaccard)

    return round(score, 4)


def search_faqs(
    query: str,
    limit: int = 3,
    min_score: float = 0.35,
) -> list[dict[str, Any]]:
    """
    Return the highest-scoring FAQ matches.

    Results below min_score are excluded.
    """
    if not isinstance(query, str):
        raise TypeError("Query must be a string.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0.0 and 1.0.")

    if not query.strip() or not tokenize(query):
        return []

    faqs = load_faqs()
    results = []

    for faq in faqs:
        score = calculate_score(query, faq)

        if score >= min_score:
            results.append({
                "id": faq["id"],
                "category": faq["category"],
                "question": faq["question"],
                "answer": faq["answer"],
                "score": score,
            })

    results.sort(key=lambda item: item["score"], reverse=True)

    return results[:limit]
