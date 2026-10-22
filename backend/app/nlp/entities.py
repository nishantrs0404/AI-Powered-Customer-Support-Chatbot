"""Entity extraction module for customer support chatbot.

Extracts domain-specific entities including Order IDs, tracking numbers,
emails, monetary amounts, and product mentions from customer messages.
"""

import re
from typing import Any
from pydantic import BaseModel, Field


# Catalog product keywords commonly found in e-commerce customer support
KNOWN_PRODUCT_KEYWORDS = {
    "laptop", "notebook", "desktop", "macbook", "chromebook",
    "phone", "smartphone", "iphone", "android",
    "headphones", "earbuds", "airpods", "headset",
    "charger", "cable", "adapter", "power bank",
    "watch", "smartwatch",
    "keyboard", "mouse", "monitor", "screen", "tablet", "ipad",
    "camera", "speaker", "microphone",
    "shoes", "sneakers", "boots",
    "shirt", "t-shirt", "jacket", "hoodie", "pants", "dress",
    "backpack", "bag", "wallet",
}


class ExtractedEntities(BaseModel):
    """Container for entities extracted from customer input."""

    order_ids: list[str] = Field(default_factory=list, description="Extracted order identifiers")
    emails: list[str] = Field(default_factory=list, description="Extracted customer email addresses")
    tracking_numbers: list[str] = Field(default_factory=list, description="Extracted shipment tracking numbers")
    amounts: list[str] = Field(default_factory=list, description="Extracted monetary amounts")
    products: list[str] = Field(default_factory=list, description="Extracted product catalog mentions")

    def has_any(self) -> bool:
        """Return True if any entity was detected."""
        return bool(
            self.order_ids
            or self.emails
            or self.tracking_numbers
            or self.amounts
            or self.products
        )

    def to_dict(self) -> dict[str, list[str]]:
        """Return entities as a standard dictionary."""
        return {
            "order_ids": self.order_ids,
            "emails": self.emails,
            "tracking_numbers": self.tracking_numbers,
            "amounts": self.amounts,
            "products": self.products,
        }


def extract_order_ids(text: str) -> list[str]:
    """Extract order identifiers matching common e-commerce formats."""
    if not text:
        return []

    patterns = [
        # Explicit order prefix: "order #12345", "order no. 98765", "order: ORD-5544"
        r"(?i)\border\s*(?:id|number|no\.?|#)?\s*[:#-]?\s*([A-Za-z0-9_-]{4,18})\b",
        # Standard prefixed code: "ORD-123456", "ORDER_98765"
        r"(?i)\b(?:ORD|ORDER)[-_][A-Za-z0-9]{4,14}\b",
        # Hash followed by digits: "#12345", "#987654"
        r"#([0-9]{4,10})\b",
    ]

    found: list[str] = []
    seen: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            # If pattern has capturing group, use it; otherwise full match
            val = match.group(1) if match.groups() else match.group(0)
            val = val.strip().lstrip("#")
            # Filter out generic words accidentally captured
            if val.lower() in {"id", "number", "no", "status", "date", "confirmation", "tracking"}:
                continue
            # Order id should contain at least some digits or be valid identifier
            if any(char.isdigit() for char in val) and val.lower() not in seen:
                seen.add(val.lower())
                found.append(val)

    return found


def extract_emails(text: str) -> list[str]:
    """Extract standard email addresses."""
    if not text:
        return []

    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    found: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(email_pattern, text):
        email = match.group(0).lower()
        if email not in seen:
            seen.add(email)
            found.append(match.group(0))

    return found


def extract_tracking_numbers(text: str) -> list[str]:
    """Extract shipment tracking numbers."""
    if not text:
        return []

    patterns = [
        # Explicit prefix: "tracking #TRK123456", "tracking number: 9400111899"
        r"(?i)\b(?:tracking|shipment|waybill)\s*(?:id|number|no\.?|#)?\s*[:#-]?\s*([A-Za-z0-9]{8,26})\b",
        # Standard carriers / formats: TRK-12345678, 1Z9999999999999999
        r"(?i)\bTRK[-_]?[0-9A-Za-z]{6,16}\b",
        r"\b1Z[0-9A-Za-z]{16}\b",
    ]

    found: list[str] = []
    seen: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            val = match.group(1) if match.groups() else match.group(0)
            val = val.strip().lstrip("#")
            if val.lower() in {"number", "id", "info", "link", "status", "update"}:
                continue
            if any(char.isdigit() for char in val) and val.lower() not in seen:
                seen.add(val.lower())
                found.append(val)

    return found


def extract_amounts(text: str) -> list[str]:
    """Extract monetary amounts (e.g. $49.99, 100 USD, 25 dollars)."""
    if not text:
        return []

    patterns = [
        # Currency symbol followed by number: $50, $49.99, €20, £15.50
        r"[\$€£]\s*[0-9]+(?:[.,][0-9]{2})?",
        # Number followed by currency word: 50 USD, 49.99 dollars, 20 euros
        r"\b[0-9]+(?:[.,][0-9]{2})?\s*(?:usd|eur|gbp|inr|cad|aud|dollars?|cents?|euros?|pounds?|bucks?)\b",
    ]

    found: list[str] = []
    seen: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            amt = match.group(0).strip()
            if amt.lower() not in seen:
                seen.add(amt.lower())
                found.append(amt)

    return found


def extract_products(text: str) -> list[str]:
    """Extract catalog product mentions."""
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    lowered = text.lower()

    for prod in sorted(KNOWN_PRODUCT_KEYWORDS, key=len, reverse=True):
        pattern = rf"\b{re.escape(prod)}s?\b"
        if re.search(pattern, lowered):
            if prod not in seen:
                seen.add(prod)
                found.append(prod)

    return found


def extract_entities(text: str) -> ExtractedEntities:
    """Extract all supported domain entities from input text."""
    if not text:
        return ExtractedEntities()

    return ExtractedEntities(
        order_ids=extract_order_ids(text),
        emails=extract_emails(text),
        tracking_numbers=extract_tracking_numbers(text),
        amounts=extract_amounts(text),
        products=extract_products(text),
    )
