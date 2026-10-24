"""Business data retrieval service.

Loads sample business data (orders, shipments, products, and policies)
from a JSON file and provides lookup functions that accept entity values
extracted by the NLP pipeline.  All lookups return plain dictionaries
(or ``None``) so the caller can decide how to present the information.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Resolve the path to the sample data relative to the project root.
_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "sample_business_data.json"

# In-memory cache so the file is only read once per process.
_cache: Optional[dict[str, Any]] = None


def _load_data(filepath: Optional[Path] = None) -> dict[str, Any]:
    """Load and cache the business data JSON file.

    Parameters
    ----------
    filepath:
        Override path used for testing.  Defaults to the project-level
        ``data/sample_business_data.json``.
    """
    global _cache  # noqa: PLW0603

    if filepath is not None:
        # Explicit path — read without caching so tests stay isolated.
        return _read_json(filepath)

    if _cache is not None:
        return _cache

    _cache = _read_json(_DATA_FILE)
    return _cache


def _read_json(filepath: Path) -> dict[str, Any]:
    """Read and parse a JSON file, returning an empty dict on failure."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if not isinstance(data, dict):
                logger.warning("Business data file is not a JSON object: %s", filepath)
                return {}
            return data
    except FileNotFoundError:
        logger.warning("Business data file not found: %s", filepath)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Malformed JSON in business data file %s: %s", filepath, exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error reading business data: %s", exc)
        return {}


def reset_cache() -> None:
    """Clear the in-memory business data cache (useful for tests)."""
    global _cache  # noqa: PLW0603
    _cache = None


def _normalize_id(value: str) -> str:
    """Normalize an identifier for comparison (case-insensitive, stripped)."""
    return value.strip().upper()


# ------------------------------------------------------------------
# Order lookup
# ------------------------------------------------------------------

def lookup_order(order_id: str, *, data: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Find an order by its order ID.

    Returns the full order record or ``None`` when not found.
    """
    if not order_id or not order_id.strip():
        return None

    source = data if data is not None else _load_data()
    orders = source.get("orders", [])
    if not isinstance(orders, list):
        return None

    target = _normalize_id(order_id)

    for order in orders:
        if not isinstance(order, dict):
            continue
        if _normalize_id(order.get("order_id", "")) == target:
            return dict(order)

    return None


# ------------------------------------------------------------------
# Shipment / tracking lookup
# ------------------------------------------------------------------

def lookup_shipment(
    *,
    order_id: Optional[str] = None,
    tracking_number: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Find shipment information by order ID or tracking number.

    At least one identifier must be provided.
    """
    if not order_id and not tracking_number:
        return None

    source = data if data is not None else _load_data()
    shipments = source.get("shipments", [])
    if not isinstance(shipments, list):
        return None

    for shipment in shipments:
        if not isinstance(shipment, dict):
            continue

        if order_id and _normalize_id(shipment.get("order_id", "")) == _normalize_id(order_id):
            return dict(shipment)

        if tracking_number and _normalize_id(shipment.get("tracking_number", "")) == _normalize_id(tracking_number):
            return dict(shipment)

    return None


# ------------------------------------------------------------------
# Product lookup
# ------------------------------------------------------------------

def lookup_product(
    *,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Find a product by ID or (partial) name.

    Name matching is case-insensitive and looks for a substring match.
    """
    if not product_id and not product_name:
        return None

    source = data if data is not None else _load_data()
    products = source.get("products", [])
    if not isinstance(products, list):
        return None

    for product in products:
        if not isinstance(product, dict):
            continue

        if product_id and _normalize_id(product.get("product_id", "")) == _normalize_id(product_id):
            return dict(product)

        if product_name:
            stored_name = product.get("name", "").lower()
            if product_name.lower() in stored_name or stored_name in product_name.lower():
                return dict(product)

    return None


# ------------------------------------------------------------------
# Policy retrieval
# ------------------------------------------------------------------

def get_return_policy(*, data: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Retrieve the return policy."""
    source = data if data is not None else _load_data()
    policies = source.get("policies", {})
    if not isinstance(policies, dict):
        return None
    policy = policies.get("return_policy")
    return dict(policy) if isinstance(policy, dict) else None


def get_refund_policy(*, data: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Retrieve the refund policy."""
    source = data if data is not None else _load_data()
    policies = source.get("policies", {})
    if not isinstance(policies, dict):
        return None
    policy = policies.get("refund_policy")
    return dict(policy) if isinstance(policy, dict) else None


def get_cancellation_policy(*, data: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Retrieve the cancellation policy."""
    source = data if data is not None else _load_data()
    policies = source.get("policies", {})
    if not isinstance(policies, dict):
        return None
    policy = policies.get("cancellation_policy")
    return dict(policy) if isinstance(policy, dict) else None


def get_shipping_policy(*, data: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """Retrieve the shipping policy."""
    source = data if data is not None else _load_data()
    policies = source.get("policies", {})
    if not isinstance(policies, dict):
        return None
    policy = policies.get("shipping_policy")
    return dict(policy) if isinstance(policy, dict) else None
