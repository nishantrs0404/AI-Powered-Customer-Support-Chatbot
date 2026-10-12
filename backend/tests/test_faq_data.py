from app.services.faq_service import load_faqs


def test_faq_dataset_contains_at_least_25_faqs():
    faqs = load_faqs()
    assert len(faqs) >= 25


def test_faq_ids_are_unique():
    faqs = load_faqs()
    ids = [faq["id"] for faq in faqs]
    assert len(ids) == len(set(ids))


def test_every_faq_has_required_fields():
    faqs = load_faqs()
    required_fields = {
        "id",
        "category",
        "question",
        "answer",
        "keywords",
    }

    for faq in faqs:
        assert required_fields.issubset(faq.keys())


def test_faq_questions_and_answers_are_not_empty():
    faqs = load_faqs()

    for faq in faqs:
        assert faq["question"].strip()
        assert faq["answer"].strip()


def test_faq_keywords_are_valid():
    faqs = load_faqs()

    for faq in faqs:
        assert isinstance(faq["keywords"], list)
        assert faq["keywords"]
        assert all(
            isinstance(keyword, str) and keyword.strip()
            for keyword in faq["keywords"]
        )


def test_faq_categories_are_not_empty():
    faqs = load_faqs()

    for faq in faqs:
        assert faq["category"].strip()
