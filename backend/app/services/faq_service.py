import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FAQ_FILE = PROJECT_ROOT / "data" / "faq.json"


def load_faqs() -> list[dict[str, Any]]:
    """Load and validate FAQs from the JSON dataset."""
    with FAQ_FILE.open("r", encoding="utf-8") as file:
        faqs = json.load(file)

    if not isinstance(faqs, list):
        raise ValueError("FAQ dataset must be a JSON list.")

    required_fields = {
        "id",
        "category",
        "question",
        "answer",
        "keywords",
    }
    seen_ids: set[str] = set()

    for index, faq in enumerate(faqs):
        if not isinstance(faq, dict):
            raise ValueError(f"FAQ at index {index} must be an object.")

        missing_fields = required_fields - faq.keys()
        if missing_fields:
            raise ValueError(
                f"FAQ at index {index} is missing: "
                f"{', '.join(sorted(missing_fields))}"
            )

        for field in ("id", "category", "question", "answer"):
            if not isinstance(faq[field], str) or not faq[field].strip():
                raise ValueError(
                    f"FAQ at index {index} has an invalid {field}."
                )

        faq_id = faq["id"]
        if faq_id in seen_ids:
            raise ValueError(f"Duplicate FAQ ID: {faq_id}")

        seen_ids.add(faq_id)

        if (
            not isinstance(faq["keywords"], list)
            or not all(
                isinstance(keyword, str) and keyword.strip()
                for keyword in faq["keywords"]
            )
        ):
            raise ValueError(
                f"FAQ {faq_id} must contain a list of non-empty keywords."
            )

    return faqs
