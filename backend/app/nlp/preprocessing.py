"""Text preprocessing utilities for customer support chatbot NLP.

Provides text cleaning, contraction expansion, normalization, and tokenization.
"""

import re
from typing import Any

# Common English contractions mapped to their expanded forms
CONTRACTION_MAP = {
    r"\bcan't\b": "cannot",
    r"\bwon't\b": "will not",
    r"\bshan't\b": "shall not",
    r"\blet's\b": "let us",
    r"\bi'm\b": "i am",
    r"\bi've\b": "i have",
    r"\bi'll\b": "i will",
    r"\bi'd\b": "i would",
    r"\byou're\b": "you are",
    r"\byou've\b": "you have",
    r"\byou'll\b": "you will",
    r"\byou'd\b": "you would",
    r"\bhe's\b": "he is",
    r"\bhe'll\b": "he will",
    r"\bhe'd\b": "he would",
    r"\bshe's\b": "she is",
    r"\bshe'll\b": "she will",
    r"\bshe'd\b": "she would",
    r"\bit's\b": "it is",
    r"\bit'll\b": "it will",
    r"\bwe're\b": "we are",
    r"\bwe've\b": "we have",
    r"\bwe'll\b": "we will",
    r"\bwe'd\b": "we would",
    r"\bthey're\b": "they are",
    r"\bthey've\b": "they have",
    r"\bthey'll\b": "they will",
    r"\bthey'd\b": "they would",
    r"\bthat's\b": "that is",
    r"\bwhat's\b": "what is",
    r"\bwhere's\b": "where is",
    r"\bwho's\b": "who is",
    r"\bhow's\b": "how is",
    r"\bthere's\b": "there is",
    r"\bhere's\b": "here is",
    r"\bisn't\b": "is not",
    r"\baren't\b": "are not",
    r"\bwasn't\b": "was not",
    r"\bweren't\b": "were not",
    r"\bhaven't\b": "have not",
    r"\bhasn't\b": "has not",
    r"\bhadn't\b": "had not",
    r"\bwon't\b": "will not",
    r"\bwouldn't\b": "would not",
    r"\bdon't\b": "do not",
    r"\bdoesn't\b": "does not",
    r"\bdidn't\b": "did not",
    r"\bcan't\b": "cannot",
    r"\bcouldn't\b": "could not",
    r"\bshouldn't\b": "should not",
    r"\bmightn't\b": "might not",
    r"\bmustn't\b": "must not",
}

# Standard English stop words for intent/keyword filtering
STOP_WORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were",
    "do", "does", "did", "can", "could", "would", "should",
    "how", "what", "when", "where", "why", "who", "which",
    "i", "me", "my", "we", "our", "you", "your", "it", "its",
    "to", "for", "of", "in", "on", "at", "and", "or",
    "please", "tell", "about", "get", "have", "has", "had",
    "be", "been", "being", "that", "this", "these", "those",
    "there", "then", "here", "if", "but", "by", "from", "with",
    "as", "just", "very", "also", "so", "than", "too",
    "t", "s", "m", "d", "ll", "ve", "re",
}


def expand_contractions(text: str) -> str:
    """Expand standard English contractions into full forms."""
    if not text:
        return ""
    result = text
    for pattern, expansion in CONTRACTION_MAP.items():
        result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)
    return result


def normalize_whitespace(text: str) -> str:
    """Collapse contiguous whitespaces into single spaces and trim boundaries."""
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str, remove_punctuation: bool = True) -> str:
    """Normalize text by expanding contractions, lowercasing, and cleaning punctuation."""
    if not text:
        return ""

    expanded = expand_contractions(text).lower()

    if remove_punctuation:
        # Keep alphanumeric, spaces, and entity markers like #, $, €
        cleaned = re.sub(r"[^\w\s#$€£-]", " ", expanded)
    else:
        cleaned = expanded

    return normalize_whitespace(cleaned)


def tokenize(text: str, remove_stopwords: bool = False, min_length: int = 1) -> list[str]:
    """Tokenize text into lowercase words with optional stopword and length filtering."""
    if not text:
        return []

    cleaned = clean_text(text, remove_punctuation=True)
    words = re.findall(r"\b[a-z0-9#-]+\b", cleaned)

    tokens = []
    for word in words:
        clean_w = word.strip("-_")
        if not clean_w or len(clean_w) < min_length:
            continue
        if remove_stopwords and clean_w in STOP_WORDS:
            continue
        tokens.append(clean_w)

    return tokens


def preprocess_text(text: str) -> dict[str, Any]:
    """Preprocess text and return structured analysis dictionary."""
    if not text:
        return {
            "raw": "",
            "normalized": "",
            "tokens": [],
            "tokens_no_stop": [],
            "char_count": 0,
            "word_count": 0,
        }

    raw = text.strip()
    normalized = clean_text(raw)
    tokens = tokenize(raw, remove_stopwords=False)
    tokens_no_stop = tokenize(raw, remove_stopwords=True)

    return {
        "raw": raw,
        "normalized": normalized,
        "tokens": tokens,
        "tokens_no_stop": tokens_no_stop,
        "char_count": len(raw),
        "word_count": len(tokens),
    }
