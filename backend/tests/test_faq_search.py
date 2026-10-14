import pytest

from app.services.faq_search import search_faqs


def test_search_finds_order_tracking_faq():
    results = search_faqs("track my order")

    assert results
    assert results[0]["id"] == "FAQ001"
    assert results[0]["score"] >= 0.35


def test_search_finds_missing_package_faq():
    results = search_faqs("Where is my package?")

    assert results
    assert results[0]["id"] == "FAQ008"


def test_search_finds_password_reset_faq():
    results = search_faqs("How do I reset my password?")

    assert results
    assert results[0]["id"] == "FAQ020"


def test_search_returns_results_in_score_order():
    results = search_faqs("order delivery tracking")

    scores = [result["score"] for result in results]

    assert scores == sorted(scores, reverse=True)


def test_search_respects_result_limit():
    results = search_faqs("order", limit=2)

    assert len(results) <= 2


def test_search_returns_empty_list_for_blank_query():
    assert search_faqs("   ") == []


def test_search_returns_empty_list_for_unrelated_query():
    results = search_faqs(
        "quantum physics and distant galaxies"
    )

    assert results == []


def test_search_rejects_invalid_limit():
    with pytest.raises(ValueError):
        search_faqs("track order", limit=0)


def test_search_rejects_non_string_query():
    with pytest.raises(TypeError):
        search_faqs(None)


def test_search_rejects_invalid_min_score():
    with pytest.raises(ValueError):
        search_faqs("track order", min_score=1.5)
